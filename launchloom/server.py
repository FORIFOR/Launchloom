from __future__ import annotations
import asyncio
import contextlib
import hmac
import json
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import __version__
from .config import Settings
from .models import Brief, BuildOptions, PublicationDraft, Approval
from .store import Store
from .pipeline import SAMPLE_BRIEF, worker_loop
from .providers import PostizPublisher, validate_publication
from .security import valid_id,safe_path,file_sha,tracking_token,scrub_error
from .rendering import validate_media, normalize_upload

WEB=Path(__file__).parent/'web'

def create_app(settings: Settings|None=None,run_worker=True):
    s=settings or Settings();s.prepare();db=Store(s.data_dir/'launchloom.sqlite3')
    stop=asyncio.Event();attempts=defaultdict(deque)
    @asynccontextmanager
    async def lifespan(app):
        task=None
        if run_worker:
            db.recover();task=asyncio.create_task(worker_loop(s,db,stop))
        yield
        stop.set()
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):await task
    app=FastAPI(title='Launchloom',version=__version__,lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.state.store=db;app.state.settings=s
    hosts=['localhost','127.0.0.1','[::1]','testserver']+[x.strip() for x in os.getenv('LAUNCHLOOM_PUBLIC_HOSTS','').split(',') if x.strip()]
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=hosts)
    def campaign(cid):
        valid_id(cid);r=db.campaign(cid)
        if not r:raise HTTPException(404,'Campaign not found')
        return r
    def root(cid):campaign(cid);return s.data_dir/'campaigns'/cid
    def publication(pid):
        valid_id(pid);r=db.publication(pid)
        if not r:raise HTTPException(404,'Publication not found')
        return r
    def auth(request):
        supplied=request.headers.get('Authorization','').removeprefix('Bearer ') or request.cookies.get('launchloom_session','')
        return bool(supplied) and hmac.compare_digest(supplied.encode(),s.token.encode())
    def throttle(key,limit=30):
        now=time.monotonic();q=attempts[key]
        while q and now-q[0]>60:q.popleft()
        if len(q)>=limit:raise HTTPException(429,'Rate limit exceeded')
        q.append(now)
        if len(attempts)>512:
            for k in list(attempts)[:256]:attempts.pop(k,None)
    @app.middleware('http')
    async def security(request: Request,call_next):
        p=request.url.path
        if request.method not in {'GET','HEAD','OPTIONS'} and p!='/collect':
            origin=request.headers.get('origin')
            if origin and origin!=str(request.base_url).rstrip('/'):
                return JSONResponse({'detail':'Cross-origin writes are not allowed'},403)
        if (p.startswith('/api/') and p!='/api/session') or p.startswith('/artifacts/'):
            if not auth(request):return JSONResponse({'detail':'Enter the local access token shown at startup.'},401)
        if request.method=='POST' and not p.endswith('/media'):
            try: content_length=int(request.headers.get('content-length','0') or 0)
            except ValueError: return JSONResponse({'detail':'Invalid Content-Length'},400)
            if content_length>2*1024*1024:
                return JSONResponse({'detail':'Request too large'},413)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"
        if p.startswith('/api/') or p.startswith('/artifacts/'):response.headers['Cache-Control']='no-store'
        return response
    @app.exception_handler(ValueError)
    async def value_error(request,e):return JSONResponse({'detail':str(e)[:500]},422)
    @app.get('/healthz')
    async def health():return {'ok':True,'version':__version__}
    @app.post('/api/session')
    async def session(request:Request):
        throttle('login:'+(request.client.host if request.client else 'local'),10)
        data=await request.json();token=str(data.get('token',''))
        if not hmac.compare_digest(token.encode(),s.token.encode()):raise HTTPException(401,'Invalid access token')
        response=JSONResponse({'ok':True})
        response.set_cookie('launchloom_session',s.token,httponly=True,samesite='strict',secure=s.secure_cookie,max_age=8*3600)
        return response
    @app.post('/api/logout')
    async def logout():
        r=JSONResponse({'ok':True});r.delete_cookie('launchloom_session');return r
    @app.get('/api/config')
    async def config():
        return {'version':__version__,'local':True,'postiz':bool(s.postiz_key and s.postiz_base),
          'live_publish':s.enable_live_publish,'fal':bool(s.fal_key and s.fal_model and s.enable_paid_generation),
          'comfy':bool(s.comfy_base),'llm':bool(s.llm_base and s.llm_model),
          'tracking':bool(s.tracking_base),'estimated_video_budget_usd':s.budget_usd,
          'capture_allowed_origins':[u for u in s.capture_origins.split(',') if u],
          'capture_sandbox':not s.no_sandbox}
    @app.get('/api/campaigns')
    async def list_campaigns():return db.campaigns()
    @app.post('/api/campaigns',status_code=201)
    async def create(brief:Brief):return db.create_campaign(brief.model_dump())
    @app.post('/api/demo',status_code=202)
    async def demo():
        c=db.create_campaign(SAMPLE_BRIEF)
        db.enqueue(c['id'],BuildOptions(capture_mode='sample').model_dump())
        return db.campaign(c['id'])
    @app.get('/api/campaigns/{cid}')
    async def get_campaign(cid:str):
        c=campaign(cid);r=root(cid)
        c['events']=db.events(cid);c['publications']=db.publications(cid)
        c['metrics']=db.metrics(cid)
        c['outputs']={}
        if c['state']=='ready':
            c['outputs']={name:f'/artifacts/{cid}/{name}' for name in ['landscape.mp4','portrait.mp4','landscape.jpg','portrait.jpg','launch-kit.zip','site/index.html','storyboard.json','manifest.json','qa.json','posts.json']}
            c['posts']=json.loads((r/'posts.json').read_text());c['qa']=json.loads((r/'qa.json').read_text());c['manifest']=json.loads((r/'manifest.json').read_text())
        return c
    @app.post('/api/campaigns/{cid}/build',status_code=202)
    async def enqueue(cid:str,options:BuildOptions):
        campaign(cid);return db.enqueue(cid,options.model_dump())
    @app.post('/api/campaigns/{cid}/media')
    async def media(cid:str,request:Request,kind:str='capture',rights_confirmed:bool=False):
        c=campaign(cid)
        if c['state']!='draft':raise HTTPException(409,'Upload before building. Finished campaigns are immutable.')
        if kind not in {'capture','audio'} or not rights_confirmed:raise HTTPException(422,'Choose capture/audio and confirm usage rights')
        dest=root(cid)/'input';dest.mkdir(parents=True,exist_ok=True)
        temp=dest/(secrets.token_hex(8)+'.part');size=0
        try:
            with temp.open('wb') as f:
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>200*1024*1024:raise HTTPException(413,'Media exceeds 200 MB')
                    f.write(chunk)
            await asyncio.to_thread(normalize_upload,temp,kind=='audio')
            if campaign(cid)['state']!='draft':raise HTTPException(409,'Campaign started while uploading; upload was discarded')
            target=dest/(kind+'.bin');temp.replace(target)
            db.log(cid,'asset',f'Operator-authorized {kind} upload: {size} bytes')
            return {'kind':kind,'bytes':size,'sha256':file_sha(target)}
        finally:temp.unlink(missing_ok=True)
    @app.get('/api/integrations')
    async def integrations():
        if not s.postiz_key or not s.postiz_base:return {'connected':False,'items':[]}
        try:return {'connected':True,'items':await PostizPublisher(s).integrations()}
        except Exception as e:raise HTTPException(502,scrub_error(e,[s.postiz_key]))
    @app.post('/api/campaigns/{cid}/publications',status_code=201)
    async def prepare_publication(cid:str,draft:PublicationDraft):
        c=campaign(cid)
        if c['state']!='ready':raise HTTPException(409,'Complete rendering and quality checks first')
        payload=draft.model_dump();file=root(cid)/draft.media
        payload['media_sha256']=file_sha(file)
        payload['ai_generated']=c['options']['film_provider']!='local'
        payload['publisher_base']=s.postiz_base
        validate_publication(payload)
        return db.create_publication(cid,payload)
    @app.get('/api/publications/{pid}/dry-run')
    async def dry_run(pid:str):
        p=publication(pid);body=validate_publication(p['payload'])
        body['posts'][0]['value'][0]['image']=[{'id':'<returned-by-upload>','path':'<returned-by-upload>'}]
        return {'dry_run':True,'network_requests':0,'fingerprint':p['fingerprint'],'postiz_body':body,
            'media_sha256':p['payload']['media_sha256'],'note':'The media is uploaded only after a separately approved live submit.'}
    @app.post('/api/publications/{pid}/approve')
    async def approve(pid:str,approval:Approval):
        p=publication(pid)
        if file_sha(root(p['campaign_id'])/p['payload']['media'])!=p['payload']['media_sha256']:raise HTTPException(409,'Media changed; create a new approval')
        return db.approve(pid,approval.fingerprint)
    @app.post('/api/publications/{pid}/submit')
    async def submit(pid:str):
        p=publication(pid)
        if not s.enable_live_publish:raise HTTPException(409,'Live publishing is disabled. Set ENABLE_LIVE_PUBLISH=1 explicitly.')
        if p['payload']['publisher_base']!=s.postiz_base:raise HTTPException(409,'Publisher destination changed; create a new approval')
        target=root(p['campaign_id'])/p['payload']['media']
        if file_sha(target)!=p['payload']['media_sha256']:raise HTTPException(409,'Approved media was changed')
        validate_publication(p['payload'])
        publisher=PostizPublisher(s)
        try:
            accounts=await publisher.integrations()
            if not isinstance(accounts,list):raise ValueError('Unexpected integrations response')
            if not any(a.get('id')==p['payload']['integration_id'] for a in accounts):raise ValueError('Destination account is not connected to this Postiz instance')
        except Exception as e:raise HTTPException(502,scrub_error(e,[s.postiz_key]))
        db.claim_publication(pid)
        try:
            receipt=await publisher.submit(p['payload'],target)
            # API acceptance != confirmed social publication.
            db.publication_result(pid,'submitted',receipt=receipt)
        except Exception as e:
            error=scrub_error(e,[s.postiz_key])
            db.publication_result(pid,'needs_reconciliation',error=error)
            raise HTTPException(502,'Submission outcome is uncertain. Inspect Postiz before repeating. '+error)
        return db.publication(pid)
    @app.get('/api/campaigns/{cid}/social-analytics')
    async def social_analytics(cid:str):
        campaign(cid);results=[]
        for p in db.publications(cid):
            if p['state']!='submitted':continue
            entries=p['receipt'] if isinstance(p['receipt'],list) else [p['receipt']]
            for entry in entries:
                if entry.get('postId'):
                    try:results.append({'post_id':entry['postId'],'source':'postiz','metrics':await PostizPublisher(s).analytics(entry['postId'])})
                    except Exception as e:results.append({'post_id':entry['postId'],'error':scrub_error(e,[s.postiz_key])})
        return {'items':results,'note':'Unavailable platform metrics remain unavailable; they are not filled with estimates.'}
    @app.post('/collect')
    async def collect(request:Request):
        if not s.tracking_base:raise HTTPException(404,'Tracking is disabled')
        throttle('collect:'+(request.client.host if request.client else 'local'),60)
        body=await request.body()
        if len(body)>4096:raise HTTPException(413,'Event too large')
        data=json.loads(body);cid=str(data.get('campaign_id',''));campaign(cid)
        if not hmac.compare_digest(str(data.get('token','')).encode(),tracking_token(s.token,cid).encode()):raise HTTPException(403,'Invalid tracking token')
        if data.get('event') not in {'page_view','cta_click'}:raise HTTPException(422,'Invalid event')
        channel=str(data.get('channel','direct'))[:32]
        db.record_metric(cid,data['event'],channel)
        # text/plain + no credentials makes tracking a simple cross-origin request; token is public, not an auth secret.
        return Response(status_code=204,headers={'Access-Control-Allow-Origin':'*'})
    @app.post('/api/campaigns/{cid}/conversions')
    async def conversion(cid:str,request:Request):
        campaign(cid);data=await request.json()
        if not data.get('verified'):raise HTTPException(422,'Send only a backend-confirmed conversion')
        db.record_metric(cid,'signup',str(data.get('channel','direct'))[:32]);return {'ok':True}
    @app.get('/artifacts/{cid}/{filename:path}')
    async def artifact(cid:str,filename:str):
        r=root(cid)
        # Raw recordings, input audio, render logs and partial files are never served.
        allowed={'landscape.mp4','portrait.mp4','landscape.jpg','portrait.jpg','launch-kit.zip','storyboard.json','manifest.json','qa.json','posts.json','social-copy.md','captions.srt','site/index.html','site/site.css','site/site.js','site/film.mp4','site/poster.jpg'}
        if filename not in allowed:raise HTTPException(404,'Asset not exposed')
        path=safe_path(r,filename)
        if not path.is_file():raise HTTPException(404,'Asset is not ready')
        return FileResponse(path,filename=path.name if filename.endswith('.zip') else None)
    @app.get('/demo-app')
    async def sample_app():return FileResponse(WEB/'demo-app.html')
    app.mount('/demo-assets',StaticFiles(directory=WEB),name='demo-assets')
    @app.get('/')
    async def index():return FileResponse(WEB/'index.html')
    app.mount('/static',StaticFiles(directory=WEB),name='static')
    return app
