"""Opt-in AI proposals, bounded quality repairs and immutable launch packages."""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import shutil
import time

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from .creative import CreativeSpec, creative_revision, fingerprint
from .creative_assistant import capabilities, public_context, request_plan, apply_operations
from .creative_quality import inspect_render, sample_frames, repair_layout
from .creative_rendering import child, file_hash, preflight
from .creative_package import write_package, zip_package
from .models import Brief

IDENTITY = re.compile(r'[a-f0-9]{32}\Z')


def register_workflow_routes(app, *, context, job, rendered, check_revision, validate_candidate, body, busy):
    db, settings = app.state.store, app.state.settings
    with db.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS creative_proposals(
          id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, base_revision TEXT NOT NULL,
          production_revision TEXT NOT NULL, candidate TEXT NOT NULL, fingerprint TEXT NOT NULL,
          report TEXT NOT NULL, created REAL NOT NULL, applied INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS creative_kits(
          id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, job_id TEXT NOT NULL, revision TEXT NOT NULL,
          brief_hash TEXT NOT NULL, sha256 TEXT NOT NULL, manifest TEXT NOT NULL, created REAL NOT NULL,
          UNIQUE(campaign_id,job_id,brief_hash));
        CREATE TABLE IF NOT EXISTS creative_ai_calls(
          id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, kind TEXT NOT NULL, state TEXT NOT NULL,
          created REAL NOT NULL, usage TEXT);
        ''')
    ai_busy = set()

    def checked(data, cid):
        values = context(cid)
        _, prod, _, _, spec, base, saved = values
        check_revision(data,spec,prod,base)
        if not saved:
            raise HTTPException(409,'Save the creative spec first')
        return values

    def persist_proposal(cid, spec, prod, plan, campaign, assets, report=None):
        candidate, changes = apply_operations(spec,plan)
        validate_candidate(candidate,campaign,assets)
        # An edit may improve an already-blocked draft. It must not introduce a new
        # unsupported renderer feature, bad source binding or short-media failure.
        old={(f['scene_id'],f['message']) for f in preflight(spec,assets)}
        if any((f['scene_id'],f['message']) not in old for f in preflight(candidate,assets)):
            raise HTTPException(422,'AI proposal needs unavailable media or unsupported rendering; no change was applied')
        result={'summary':plan.summary,'warnings':plan.warnings,'changes':changes,
                'candidate_revision':creative_revision(candidate),'base_revision':creative_revision(spec),
                'production_revision':prod['revision'], 'saved':False, 'published':False,
                'report':report or {}}
        pid=secrets.token_hex(16)
        fp=fingerprint({'campaign_id':cid,'proposal_id':pid,'candidate':candidate.model_dump(),'result':result})
        with db.connect() as c:
            if c.execute('SELECT count(*) FROM creative_proposals WHERE campaign_id=?',(cid,)).fetchone()[0]>=100:
                raise HTTPException(409,'This campaign reached its 100 proposal limit')
            c.execute('INSERT INTO creative_proposals VALUES(?,?,?,?,?,?,?,?,0)',
                      (pid,cid,creative_revision(spec),prod['revision'],candidate.model_dump_json(),fp,json.dumps(result),time.time()))
        return {**result,'id':pid,'fingerprint':fp}

    async def model_call(cid, kind, data_context, frames=None):
        if ai_busy:
            raise HTTPException(409,'Another creative AI request is running')
        if not capabilities(settings)['enabled']:
            raise HTTPException(422,'Configure and explicitly enable the creative AI provider first')
        call=secrets.token_hex(16)
        with db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT count(*) FROM creative_ai_calls WHERE created>?',(time.time()-3600,)).fetchone()[0]>=20:
                raise HTTPException(429,'20 AI attempts per hour reached, including failed or uncertain requests')
            c.execute('INSERT INTO creative_ai_calls VALUES(?,?,?,?,?,NULL)',(call,cid,kind,'started',time.time()))
        ai_busy.add(call)
        try:
            plan,usage=await request_plan(settings,data_context,frames)
            with db.connect() as c:
                c.execute('UPDATE creative_ai_calls SET state=?,usage=? WHERE id=?',('returned',json.dumps(usage),call))
            return plan,usage
        except BaseException:
            with db.connect() as c:
                c.execute('UPDATE creative_ai_calls SET state=? WHERE id=?',('failed_or_uncertain',call))
            raise
        finally:
            ai_busy.discard(call)

    @app.get('/api/campaigns/{cid}/creative-workflow')
    async def workflow(cid: str):
        context(cid,include_assets=False)
        return {'assistant':capabilities(settings),'local_repairs':True,'launch_package':True,
                'automatic_publishing':False,'max_repair_passes':3,
                'external_verification':{'paid_video':'not_verified_here','after_effects':'not_verified_here','social_publish':'not_verified_here'}}

    @app.post('/api/campaigns/{cid}/creative-spec/ai-proposal')
    async def ai_edit(cid: str, request: Request):
        data=await body(request,{'expected_revision','production_revision','instruction','external_data_consent'})
        _,prod,campaign,assets,spec,_,_=checked(data,cid)
        instruction=data['instruction']
        if data['external_data_consent'] is not True:
            raise HTTPException(422,'Confirm sending the instruction, brand notes and public scene copy to the configured provider; this may incur charges')
        if not isinstance(instruction,str) or not 1<=len(instruction.strip())<=2000:
            raise HTTPException(422,'Use a creative instruction of 1–2000 characters')
        plan,usage=await model_call(cid,'edit',public_context(spec,campaign['brief'],instruction))
        # Even a valid response is stale if either editor changed during the call.
        checked(data,cid)
        return persist_proposal(cid,spec,prod,plan,campaign,assets,{'kind':'configured_ai','usage':usage,'provider_calls':1})

    @app.post('/api/campaigns/{cid}/creative-spec/repair-proposal')
    async def local_repair(cid: str, request: Request):
        data=await body(request,{'expected_revision','production_revision','max_passes'})
        _,prod,campaign,assets,spec,_,_=checked(data,cid)
        plan,report=await asyncio.to_thread(repair_layout,spec,data['max_passes'])
        checked(data,cid)
        return persist_proposal(cid,spec,prod,plan,campaign,assets,{'kind':'measured_local_repair',**report})

    @app.post('/api/campaigns/{cid}/creative-proposals/{pid}/apply')
    async def apply(cid: str, pid: str, request: Request):
        data=await body(request,{'fingerprint','content_reviewed','expected_revision','production_revision'})
        if not IDENTITY.fullmatch(pid):
            raise HTTPException(404,'Proposal not found')
        if data['content_reviewed'] is not True:
            raise HTTPException(422,'Review the exact copy and proposed changes before applying')
        _,prod,campaign,assets,spec,base,_=context(cid)
        if cid in busy:
            raise HTTPException(409,'Another production action is running')
        with db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            p=c.execute('SELECT * FROM creative_proposals WHERE id=? AND campaign_id=?',(pid,cid)).fetchone()
            if not p:
                raise HTTPException(404,'Proposal not found')
            if p['fingerprint']!=data['fingerprint']:
                raise HTTPException(409,'Proposal fingerprint does not match the reviewed changes')
            if p['base_revision']!=data['expected_revision'] or p['production_revision']!=data['production_revision'] or base!=prod['revision'] or prod['revision']!=p['production_revision']:
                raise HTTPException(409,'Proposal source changed. Request a new proposal')
            candidate=CreativeSpec.model_validate_json(p['candidate'])
            validate_candidate(candidate,campaign,assets)
            now=c.execute('SELECT revision FROM creative_specs WHERE campaign_id=?',(cid,)).fetchone()
            if p['applied']:
                if not now or now['revision']!=creative_revision(candidate):
                    raise HTTPException(409,'This proposal was already applied and the composition later changed')
            else:
                if p['created']<time.time()-3600:
                    raise HTTPException(409,'Proposal expired after one hour; request a new one')
                if not now or now['revision']!=p['base_revision']:
                    raise HTTPException(409,'Composition changed after the proposal. Reload first')
                if c.execute("SELECT id FROM creative_jobs WHERE campaign_id=? AND state IN ('queued','running')",(cid,)).fetchone():
                    raise HTTPException(409,'Rendering is in progress')
                c.execute('UPDATE creative_specs SET spec=?,revision=?,updated=? WHERE campaign_id=?',
                          (candidate.model_dump_json(),creative_revision(candidate),time.time(),cid))
                c.execute('UPDATE creative_proposals SET applied=1 WHERE id=?',(pid,))
                c.execute('INSERT INTO events(campaign_id,kind,message,created) VALUES(?,?,?,?)',
                          (cid,'creative',f'Applied reviewed proposal {pid}. Finished films and posts unchanged.',time.time()))
        return {'spec':candidate.model_dump(),'revision':creative_revision(candidate),'production_revision':base,'saved':True,'published':False}

    @app.get('/api/campaigns/{cid}/creative-renders/{jid}/quality/{output}')
    async def quality(cid: str, jid: str, output: str):
        row,path=rendered(cid,jid,output)
        stored=json.loads(row['result']).get('quality_review',{}).get(output)
        if stored:
            return stored
        spec=CreativeSpec.model_validate_json(row['spec'])
        return await asyncio.to_thread(inspect_render,spec,path,output,
            json.loads(row['result'])['outputs'][output]['sha256'],row['scene_id'])

    @app.post('/api/campaigns/{cid}/creative-renders/{jid}/visual-review')
    async def visual(cid: str, jid: str, request: Request):
        data=await body(request,{'expected_revision','production_revision','output','external_data_consent','frames_reviewed'})
        _,prod,campaign,assets,spec,_,_=checked(data,cid)
        if data['external_data_consent'] is not True or data['frames_reviewed'] is not True:
            raise HTTPException(422,'Review the rendered film and explicitly consent to sending up to six sampled frames and scene copy to the configured vision provider')
        if not capabilities(settings)['vision_enabled']:
            raise HTTPException(422,'Explicitly enable a vision-capable provider first')
        if data['output'] not in ('landscape','portrait'):
            raise HTTPException(422,'Choose an output')
        row,path=rendered(cid,jid,data['output'])
        if row['revision']!=creative_revision(spec) or row['scene_id'] is not None:
            raise HTTPException(409,'Visual review requires a complete render of the current saved revision')
        sha=json.loads(row['result'])['outputs'][data['output']]['sha256']
        frames=await asyncio.to_thread(sample_frames,spec,path,data['output'])
        if file_hash(path)!=sha:
            raise HTTPException(409,'Media changed while sampling')
        ctx=public_context(spec,campaign['brief'],'映像の読みやすさと構図を確認して、必要な部分だけ修正してください。' if campaign['brief'].get('language')=='ja' else 'Review readability and composition; propose only necessary small changes.')
        plan,usage=await model_call(cid,'sampled_visual_review',ctx,frames)
        checked(data,cid)
        return persist_proposal(cid,spec,prod,plan,campaign,assets,
               {'kind':'sampled_visual_review','usage':usage,'provider_calls':1,'render_id':jid,'media_sha256':sha,
                'sample_count':len(frames),'findings':[f.model_dump() for f in plan.findings],
                'motion_assessed':False,'audio_assessed':False})

    def kit(cid,kid):
        root=context(cid,include_assets=False)[0]
        if not IDENTITY.fullmatch(kid):
            raise HTTPException(404,'Kit not found')
        with db.connect() as c:
            record=c.execute('SELECT * FROM creative_kits WHERE id=? AND campaign_id=?',(kid,cid)).fetchone()
        if not record:
            raise HTTPException(404,'Kit not found')
        folder=child(root,'creative-kits',kid)
        archive=child(folder,'launch-kit.zip')
        if not archive.is_file() or file_hash(archive)!=record['sha256']:
            raise HTTPException(409,'Kit changed or is missing; do not publish it')
        return record,folder,archive

    def kit_result(cid, record):
        return {'id':record['id'],'revision':record['revision'],'sha256':record['sha256'],
                'manifest':json.loads(record['manifest']),'published':False,'deployed':False,
                'download_url':f"/api/campaigns/{cid}/creative-kits/{record['id']}/download",
                'preview_url':f"/api/campaigns/{cid}/creative-kits/{record['id']}/files/site/index.html"}

    @app.post('/api/campaigns/{cid}/creative-renders/{jid}/kit',status_code=201)
    async def export(cid: str,jid: str,request: Request):
        data=await body(request,{'expected_revision','production_revision','content_reviewed','rights_confirmed'})
        root,prod,campaign,_,spec,_,_=checked(data,cid)
        if data['content_reviewed'] is not True or data['rights_confirmed'] is not True:
            raise HTTPException(422,'Review the exact scene copy and media, and confirm usage rights before packaging')
        row=job(cid,jid)
        if row['state']!='ready' or row['scene_id'] is not None or row['revision']!=creative_revision(spec):
            raise HTTPException(409,'Package a complete render of the current saved composition')
        brief=Brief.model_validate(campaign['brief'])
        # Bound deduplication to the brief too (destination URL, language/channels).
        brief_hash=fingerprint(brief.model_dump())
        with db.connect() as c:
            old=c.execute('SELECT * FROM creative_kits WHERE campaign_id=? AND job_id=? AND brief_hash=?',(cid,jid,brief_hash)).fetchone()
            if c.execute('SELECT count(*) FROM creative_kits WHERE campaign_id=?',(cid,)).fetchone()[0]>=10 and not old:
                raise HTTPException(409,'This campaign reached its ten-kit limit')
        if old:
            kit(cid,old['id'])
            return kit_result(cid,old)
        if cid in busy:
            raise HTTPException(409,'Another production action is running')
        sources={}
        for output in spec.outputs:
            _,source=rendered(cid,jid,output)
            sources[output]=(source,json.loads(row['result'])['outputs'][output]['sha256'])
        kid=secrets.token_hex(16);folder=child(root,'creative-kits',kid)
        folder.parent.mkdir(parents=True,exist_ok=True)
        busy.add(cid);committed=False;future=None
        def build():
            manifest=write_package(spec,brief,cid,sources,folder)
            archive=child(folder,'launch-kit.zip');zip_package(folder,archive)
            return manifest,file_hash(archive)
        try:
            future=asyncio.create_task(asyncio.to_thread(build))
            manifest,sha=await asyncio.shield(future)
            checked(data,cid)
            with db.connect() as c:
                c.execute('INSERT INTO creative_kits VALUES(?,?,?,?,?,?,?,?)',
                          (kid,cid,jid,creative_revision(spec),brief_hash,sha,json.dumps(manifest),time.time()))
                record=c.execute('SELECT * FROM creative_kits WHERE id=?',(kid,)).fetchone()
            committed=True
            return kit_result(cid,record)
        except asyncio.CancelledError:
            if future:
                try:await future
                except Exception:pass
            raise
        finally:
            if not committed:shutil.rmtree(folder,ignore_errors=True)
            busy.discard(cid)

    @app.get('/api/campaigns/{cid}/creative-kits/{kid}/download')
    async def download(cid: str,kid: str):
        record,_,path=kit(cid,kid)
        return FileResponse(path,media_type='application/zip',filename='launchloom-'+record['revision'][:12]+'.zip')

    @app.get('/api/campaigns/{cid}/creative-kits/{kid}/files/{name:path}')
    async def member(cid: str,kid: str,name: str):
        record,folder,_=kit(cid,kid)
        manifest=json.loads(record['manifest'])
        if name not in manifest['files']:
            raise HTTPException(404,'Kit member not found')
        path=child(folder,*name.split('/'))
        if not path.is_file() or file_hash(path)!=manifest['files'][name]:
            raise HTTPException(409,'Kit member changed')
        return FileResponse(path)
