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
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import __version__
from .config import Settings
from .models import Brief, BuildOptions, PublicationDraft, Approval, PlanEdit, Reconciliation
from .store import Store
from .pipeline import SAMPLE_BRIEF, SAMPLES, worker_loop
from .planning import apply_plan_edit
from .providers import PostizPublisher, validate_publication, receipt_ids, match_remote, remote_candidates, REMOTE_STATES, CHANNEL_SETTINGS, CHANNEL_LIMITS
from .security import valid_id,safe_path,file_sha,tracking_token,conversion_secret,signed_body,scrub_error
from .rendering import validate_media, normalize_upload
from .deploy import plan as deployment_plan, publish as deploy_site
from .finished_films import list_films, checked_film, FINAL_MEDIA, register_finished_routes
from .production_api import register_production_routes
from .planning import make_posts

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
          'capture_sandbox':not s.no_sandbox,
          'channel_settings':CHANNEL_SETTINGS,'channel_limits':CHANNEL_LIMITS,
          'max_posts_per_channel_per_day':s.max_posts_per_channel_per_day,
          'min_post_gap_minutes':s.min_post_gap_minutes,
          'deploy_target_configured':bool(s.deploy_dir)}
    @app.get('/api/campaigns')
    async def list_campaigns():return db.campaigns()
    @app.post('/api/campaigns',status_code=201)
    async def create(brief:Brief):return db.create_campaign(brief.model_dump())
    @app.post('/api/demo',status_code=202)
    async def demo(language:str='ja'):
        c=db.create_campaign(SAMPLES.get(language,SAMPLE_BRIEF))
        db.enqueue(c['id'],BuildOptions(capture_mode='sample').model_dump())
        return db.campaign(c['id'])
    @app.get('/api/campaigns/{cid}')
    async def get_campaign(cid:str):
        c=campaign(cid);r=root(cid)
        c['events']=db.events(cid);c['publications']=db.publications(cid)
        c['metrics']=db.metrics(cid)
        c['outputs']={}
        if c['state']=='awaiting_review' and (r/'review-frame.jpg').is_file():
            c['outputs']={'review-frame.jpg':f'/artifacts/{cid}/review-frame.jpg'}
        if c['state']=='ready':
            c['outputs']={name:f'/artifacts/{cid}/{name}' for name in ['landscape.mp4','portrait.mp4','landscape.jpg','portrait.jpg','launch-kit.zip','site/index.html','storyboard.json','manifest.json','qa.json','posts.json']}
            c['posts']=json.loads((r/'posts.json').read_text());c['qa']=json.loads((r/'qa.json').read_text());c['manifest']=json.loads((r/'manifest.json').read_text())
        c['final_films']=list_films(db,cid)
        for film in c['final_films']: c['outputs'][film['media']]=film['url']
        if c['final_films'] and c['state']!='ready':
            c['posts']=make_posts(Brief.model_validate(c['brief']),cid)
        return c
    @app.post('/api/campaigns/{cid}/build',status_code=202)
    async def enqueue(cid:str,options:BuildOptions):
        campaign(cid);return db.enqueue(cid,options.model_dump())
    @app.patch('/api/campaigns/{cid}/plan')
    async def edit_plan(cid:str,edit:PlanEdit):
        c=campaign(cid)
        if c['state'] not in {'awaiting_review','ready'}:raise HTTPException(409,'A storyboard can be reworded while it waits for review, or after it is finished')
        if not c['plan']:raise HTTPException(409,'There is no storyboard to edit yet')
        updated=apply_plan_edit(c['plan'],edit)
        db.log(cid,'review','構成を編集しました（文言は制作者によるもの）。')
        return db.save_plan(cid,updated)
    @app.post('/api/campaigns/{cid}/render',status_code=202)
    async def approve_plan(cid:str):
        c=campaign(cid)
        if c['state']!='awaiting_review':raise HTTPException(409,'This campaign is not waiting for a storyboard review')
        db.save_plan(cid,c['plan'],approved=True)
        db.log(cid,'review','構成を承認しました。レンダリングを開始します。')
        return db.enqueue(cid,c['options'],revision=True)
    @app.post('/api/campaigns/{cid}/revise',status_code=202)
    async def revise(cid:str,edit:PlanEdit|None=None):
        """Re-render a finished campaign from material it already has.

        The recording is reused and no provider request is repeated: only the
        composition changes, so one scene or CTA can be fixed on its own."""
        c=campaign(cid)
        if c['state']!='ready':raise HTTPException(409,'Only a finished campaign can be revised')
        plan=apply_plan_edit(c['plan'],edit) if edit else c['plan']
        db.save_plan(cid,plan,approved=True)
        db.log(cid,'review','この素材のまま、構成を作り直します。再収録と生成AIへの再依頼は行いません。')
        return db.enqueue(cid,c['options'],revision=True)
    @app.post('/api/campaigns/{cid}/release')
    async def release(cid:str,request:Request):
        c=campaign(cid)
        if c['state']!='ready' and not list_films(db,cid):raise HTTPException(409,'Finish or import a film before releasing it')
        data=await request.json()
        if not data.get('confirmed'):raise HTTPException(422,'Releasing a campaign is an explicit confirmation')
        db.log(cid,'release','キャンペーンを公開可能にしました。個々の投稿は、引き続き投稿ごとの承認が必要です。')
        return db.release_campaign(cid,True)
    @app.post('/api/campaigns/{cid}/hold')
    async def hold(cid:str):
        c=campaign(cid)
        db.log(cid,'release','公開を保留にしました。未送信の投稿は送信できません。')
        return db.release_campaign(cid,False)
    @app.post('/api/campaigns/{cid}/media')
    async def media(cid:str,request:Request,kind:str='capture',rights_confirmed:bool=False):
        c=campaign(cid)
        if c['state']!='draft':raise HTTPException(409,'Upload before building. Finished campaigns are immutable.')
        if kind not in {'capture','audio','narration'} or not rights_confirmed:raise HTTPException(422,'Choose capture/audio/narration and confirm usage rights')
        dest=root(cid)/'input';dest.mkdir(parents=True,exist_ok=True)
        temp=dest/(secrets.token_hex(8)+'.part');size=0
        try:
            with temp.open('wb') as f:
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>200*1024*1024:raise HTTPException(413,'Media exceeds 200 MB')
                    f.write(chunk)
            await asyncio.to_thread(normalize_upload,temp,kind in {'audio','narration'})
            if campaign(cid)['state']!='draft':raise HTTPException(409,'Campaign started while uploading; upload was discarded')
            target=dest/(kind+'.bin');temp.replace(target)
            db.log(cid,'asset',f'Operator-authorized {kind} upload: {size} bytes')
            return {'kind':kind,'bytes':size,'sha256':file_sha(target)}
        finally:temp.unlink(missing_ok=True)
    def check_pacing(cid,payload,pid=None):
        """Keep a campaign from stacking up on one channel.

        Counts every publication this studio has approved or submitted, so a
        variant cannot slip past by being created separately."""
        now=datetime.now(timezone.utc)
        when=datetime.fromisoformat(payload['schedule_at'].replace('Z','+00:00')) if payload.get('schedule_at') else now
        same_day=0
        for entry in db.channel_schedule(cid,payload['channel']):
            if entry['id']==pid:continue
            if entry['state'] not in {'approved','submitting','submitted','needs_reconciliation'}:continue
            other=datetime.fromisoformat(entry['at'].replace('Z','+00:00')) if entry['at'] else datetime.fromtimestamp(entry['created'],timezone.utc)
            gap=abs((when-other).total_seconds())
            if gap<s.min_post_gap_minutes*60:
                raise HTTPException(409,f"Another {payload['channel']} post is within {s.min_post_gap_minutes} minutes. Space variants out or change the schedule.")
            if gap<86400:same_day+=1
        if same_day>=s.max_posts_per_channel_per_day:
            raise HTTPException(409,f"This campaign already has {s.max_posts_per_channel_per_day} {payload['channel']} posts within a day. Raise MAX_POSTS_PER_CHANNEL_PER_DAY deliberately if that is intended.")
    @app.get('/api/integrations')
    async def integrations():
        if not s.postiz_key or not s.postiz_base:return {'connected':False,'items':[]}
        try:return {'connected':True,'items':await PostizPublisher(s).integrations()}
        except Exception as e:raise HTTPException(502,scrub_error(e,[s.postiz_key]))
    @app.post('/api/campaigns/{cid}/publications',status_code=201)
    async def prepare_publication(cid:str,draft:PublicationDraft):
        c=campaign(cid)
        payload=draft.model_dump()
        if FINAL_MEDIA.fullmatch(draft.media):
            film,file=checked_film(db,s.data_dir,cid,draft.media)
            payload['ai_generated']=bool(film['ai_generated'])
        else:
            if c['state']!='ready':raise HTTPException(409,'Complete rendering or choose an imported final film first')
            file=root(cid)/draft.media
            payload['ai_generated']=c['options']['film_provider']!='local'
        payload['media_sha256']=file_sha(file)
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
        if FINAL_MEDIA.fullmatch(p['payload']['media']):checked_film(db,s.data_dir,p['campaign_id'],p['payload']['media'])
        if file_sha(root(p['campaign_id'])/p['payload']['media'])!=p['payload']['media_sha256']:raise HTTPException(409,'Media changed; create a new approval')
        check_pacing(p['campaign_id'],p['payload'],pid)
        return db.approve(pid,approval.fingerprint)
    @app.post('/api/publications/{pid}/submit')
    async def submit(pid:str):
        p=publication(pid)
        if not s.enable_live_publish:raise HTTPException(409,'Live publishing is disabled. Set ENABLE_LIVE_PUBLISH=1 explicitly.')
        if not campaign(p['campaign_id'])['released']:raise HTTPException(409,'Release the campaign before anything is sent. Finishing a film is not a decision to publish it.')
        if p['payload']['publisher_base']!=s.postiz_base:raise HTTPException(409,'Publisher destination changed; create a new approval')
        target=root(p['campaign_id'])/p['payload']['media']
        if FINAL_MEDIA.fullmatch(p['payload']['media']):_,target=checked_film(db,s.data_dir,p['campaign_id'],p['payload']['media'])
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
    def publication_window(p):
        at=p['payload'].get('schedule_at')
        moment=datetime.fromisoformat(at.replace('Z','+00:00')) if at else datetime.fromtimestamp(p['created'],timezone.utc)
        return moment-timedelta(days=2),moment+timedelta(days=2)
    @app.get('/api/campaigns/{cid}/deployment-preview')
    async def deployment_preview(cid:str):
        c=campaign(cid)
        if c['state']!='ready':raise HTTPException(409,'Finish the campaign before previewing a deployment')
        return deployment_plan(root(cid),s)
    @app.post('/api/campaigns/{cid}/deploy')
    async def deploy(cid:str,request:Request):
        """Copy the approved landing page into the operator's own directory."""
        c=campaign(cid)
        if c['state']!='ready':raise HTTPException(409,'Finish the campaign before deploying it')
        if not c['released']:raise HTTPException(409,'Release the campaign before its landing page goes anywhere')
        data=await request.json()
        if not data.get('confirmed'):raise HTTPException(422,'Confirm the previewed files before deploying')
        result=await asyncio.to_thread(deploy_site,root(cid),s,str(data.get('fingerprint','')))
        db.log(cid,'deploy',f"ランディングページを {result['target']} へ書き出しました。配信はホスティング側の設定に依存します。")
        return result
    @app.get('/api/campaigns/{cid}/publication-states')
    async def publication_states(cid:str):
        """Ask Postiz what actually happened. Acceptance is not publication, so the
        remote state is stored separately from our own submission record."""
        campaign(cid);results=[]
        for p in db.publications(cid):
            if p['state'] not in {'submitted','needs_reconciliation'}:continue
            ids=receipt_ids(p['receipt'])
            entry={'id':p['id'],'channel':p['payload']['channel'],'state':p['state'],'remote_ids':ids}
            if not ids:
                entry['remote_state']='unknown';entry['note']='Postizの投稿IDが記録されていません。突合が必要です。'
                results.append(entry);continue
            try:
                start,end=publication_window(p)
                found=match_remote(await PostizPublisher(s).posts(start,end),ids)
            except Exception as e:
                entry['error']=scrub_error(e,[s.postiz_key]);results.append(entry);continue
            if found:
                remote=REMOTE_STATES.get(str(found.get('state','')),str(found.get('state','')).lower() or 'unknown')
                url=found.get('releaseURL') or None
                db.record_remote_state(p['id'],remote,url)
                entry.update(remote_state=remote,remote_url=url)
            else:
                db.record_remote_state(p['id'],'absent',None)
                entry.update(remote_state='absent',note='この期間のPostizに該当の投稿が見つかりません。')
            results.append(entry)
        return {'items':results,'note':'Postizが保持している状態です。各SNS上の表示は、必要なら現地で確認してください。'}
    @app.get('/api/publications/{pid}/candidates')
    async def candidates(pid:str):
        """Same-account posts with the same opening text, for an operator deciding
        whether an uncertain submission created something."""
        p=publication(pid)
        try:
            start,end=publication_window(p)
            posts=await PostizPublisher(s).posts(start,end)
        except Exception as e:raise HTTPException(502,scrub_error(e,[s.postiz_key]))
        found=match_remote(posts,receipt_ids(p['receipt']))
        return {'exact':found,'candidates':remote_candidates(posts,p['payload']['integration_id'],p['payload']['content']),
            'window':[start.isoformat(),end.isoformat()],
            'note':'一致は制作者が判断します。自動で「投稿済み」とは記録しません。'}
    @app.post('/api/publications/{pid}/reconcile')
    async def reconcile(pid:str,decision:Reconciliation):
        p=publication(pid)
        if p['state']!='needs_reconciliation':raise HTTPException(409,'This publication is not waiting for reconciliation')
        if decision.resolution=='published':
            db.publication_result(pid,'submitted',receipt=[{'postId':decision.remote_id,'source':'operator-reconciled','note':decision.note}])
            db.record_remote_state(pid,'published',None)
            db.log(p['campaign_id'],'publish',f'送信結果を突合しました：投稿は存在します（{decision.remote_id}）。')
        else:
            db.publication_result(pid,'approved',error=None)
            db.log(p['campaign_id'],'publish','送信結果を突合しました：投稿は作成されていません。承認済みに戻したので、必要なら送信し直せます。')
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
    @app.get('/api/campaigns/{cid}/conversion-key')
    async def conversion_key(cid:str):
        """The signing key an operator's backend uses to report real signups.

        It is derived from the studio token for this campaign only, so a backend
        can post conversions without being able to read or change anything else."""
        campaign(cid)
        return {'campaign_id':cid,'endpoint':'/conversions','secret':conversion_secret(s.token,cid),
            'how':'POST /conversions with header X-Launchloom-Signature: sha256=HMAC_SHA256(secret, raw_body). '
                  'Body: {"campaign_id","conversion_id","channel","at"}. Send no personal data: '
                  'conversion_id should be an opaque id from your own system.'}
    @app.post('/conversions')
    async def conversion(request:Request):
        """A conversion your backend confirmed. Signed, deduplicated, and never
        inferred from a page view."""
        throttle('conversion:'+(request.client.host if request.client else 'local'),120)
        body=await request.body()
        if len(body)>2048:raise HTTPException(413,'Conversion payload too large')
        data=json.loads(body);cid=str(data.get('campaign_id',''))
        campaign(cid)
        supplied=request.headers.get('X-Launchloom-Signature','')
        if not hmac.compare_digest(supplied,signed_body(conversion_secret(s.token,cid),body)):
            raise HTTPException(403,'Invalid conversion signature')
        identifier=str(data.get('conversion_id',''))
        if not 1<=len(identifier)<=120:raise HTTPException(422,'Give each conversion a unique id from your own system')
        at=str(data.get('at',''))
        if at:
            try:moment=datetime.fromisoformat(at.replace('Z','+00:00'))
            except ValueError:raise HTTPException(422,'`at` must be an ISO timestamp with a timezone')
            if moment.tzinfo is None:raise HTTPException(422,'`at` must include a timezone')
            if abs((datetime.now(timezone.utc)-moment).total_seconds())>300:
                raise HTTPException(422,'Conversion timestamp is outside the five minute replay window')
        counted=db.record_metric(cid,'signup',str(data.get('channel','direct'))[:32],dedupe_key=cid+':'+identifier)
        # A repeat is a successful no-op: a retrying backend must not inflate results.
        return {'ok':True,'counted':counted,'duplicate':not counted}
    @app.get('/artifacts/{cid}/{filename:path}')
    async def artifact(cid:str,filename:str):
        r=root(cid)
        # Raw recordings, input audio, render logs and partial files are never served.
        allowed={'landscape.mp4','portrait.mp4','landscape.jpg','portrait.jpg','launch-kit.zip','storyboard.json','manifest.json','qa.json','posts.json','social-copy.md','captions.srt','site/index.html','site/site.css','site/site.js','site/film.mp4','site/poster.jpg','review-frame.jpg'}
        if FINAL_MEDIA.fullmatch(filename):
            try: _,path=checked_film(db,s.data_dir,cid,filename)
            except ValueError as e:raise HTTPException(404,'Final film unavailable') from e
        else:
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
    register_production_routes(app)
    register_finished_routes(app)
    return app
