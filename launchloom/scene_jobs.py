"""Durable, explicitly authorized Seedance scene jobs via fal's queue API.

Only the selected scene prompt is sent. A retry reuses FalFilm's stored request,
not a new provider submission. No job releases a campaign or approves a post.
"""
from __future__ import annotations
import asyncio
import json
import math
import os
import time
import secrets
from dataclasses import replace
from pathlib import Path
from typing import Literal
from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import Field, StrictBool
from .models import StrictModel, BuildOptions
from .production import validate_plan, initial_plan, revision
from .providers import FalFilm
from .security import digest, valid_id, scrub_error
from .rendering import validate_media

SEEDANCE_MODEL = 'bytedance/seedance-2.5/text-to-video'


class SceneGeneration(StrictModel):
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    scene_id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,39}$')
    resolution: Literal['480p', '720p'] = '480p'
    generate_audio: StrictBool = True
    take: int = Field(default=0, ge=0, le=50)
    estimated_cost_usd: float = Field(gt=0, le=100, allow_inf_nan=False)
    external_data_consent: StrictBool
    charge_confirmed: StrictBool


class SceneJobs:
    def __init__(self, db, settings):
        self.db, self.s = db, settings
        with db.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS scene_jobs(
                id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, fingerprint TEXT NOT NULL UNIQUE,
                spec TEXT NOT NULL, state TEXT NOT NULL, error TEXT, created REAL NOT NULL,
                updated REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS scene_jobs_state ON scene_jobs(state,created);''')

    def root(self, cid):
        valid_id(cid)
        c = self.db.campaign(cid)
        if not c: raise HTTPException(404, 'Campaign not found')
        base = self.s.data_dir.resolve()/'campaigns'
        root = base/cid
        if base.is_symlink() or root.is_symlink() or root.resolve().parent != base:
            raise HTTPException(400, 'Invalid campaign path')
        return root

    def folder(self, cid, jid):
        valid_id(jid)
        base = self.root(cid)/'scene-jobs'
        folder = base/jid
        if base.is_symlink() or folder.is_symlink():
            raise HTTPException(400, 'Invalid job directory')
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def plan(self, cid):
        path = self.root(cid)/'production-plan.json'
        if path.is_symlink(): raise HTTPException(400, 'Invalid production file')
        return validate_plan(json.loads(path.read_text())) if path.is_file() else initial_plan(self.db.campaign(cid)['brief'])

    @staticmethod
    def decode(row):
        if row is None: return None
        r = dict(row);r['spec'] = json.loads(r['spec'])
        if r['state']=='ready':r['media_url']=f"/api/campaigns/{r['campaign_id']}/scene-jobs/{r['id']}/media"
        return r

    def get(self, cid, jid):
        valid_id(jid);self.root(cid)
        with self.db.connect() as c:
            row = c.execute('SELECT * FROM scene_jobs WHERE campaign_id=? AND id=?', (cid,jid)).fetchone()
        if not row: raise HTTPException(404,'Scene job not found')
        return self.decode(row)

    def list(self, cid):
        self.root(cid)
        with self.db.connect() as c:
            rows=c.execute('SELECT * FROM scene_jobs WHERE campaign_id=? ORDER BY created DESC LIMIT 100', (cid,)).fetchall()
        return [self.decode(r) for r in rows]

    def enqueue(self, cid, request):
        if not request.external_data_consent or not request.charge_confirmed:
            raise HTTPException(422,'Confirm scene-data transmission and generation cost')
        if not self.s.enable_paid_generation or not self.s.fal_key:
            raise HTTPException(409,'Set FAL_KEY and ENABLE_PAID_GENERATION=1 on the server first')
        if not math.isfinite(self.s.budget_usd) or self.s.budget_usd<=0:
            raise HTTPException(409,'Set a positive GENERATION_BUDGET_USD before generation')
        plan=self.plan(cid)
        if revision(plan)!=request.expected_revision:
            raise HTTPException(409,'Plan changed; save and review the current scene again')
        scene=next((x for x in plan['scenes'] if x['id']==request.scene_id),None)
        if not scene or scene['source']!='seedance':raise HTTPException(422,'Select a Seedance scene')
        seconds=scene['seconds']
        if seconds!=int(seconds) or not 4<=seconds<=30:
            raise HTTPException(422,'Seedance 2.5 requires a whole number of seconds between 4 and 30')
        if not scene['prompt'].strip():raise HTTPException(422,'Write a visual prompt for the scene')
        # Headings, private evidence, product description, other scenes and account
        # credentials are deliberately absent from the model input.
        inputs={'prompt':scene['prompt'],'duration':str(int(seconds)),
                'aspect_ratio':plan['aspect_ratio'],'resolution':request.resolution,
                'generate_audio':request.generate_audio}
        end_user=os.getenv('SEEDANCE_END_USER_ID','').strip()
        if end_user:inputs['end_user_id']=end_user[:200]
        spec={'model':SEEDANCE_MODEL,'input':inputs,'scene_id':scene['id'],
              'plan_revision':request.expected_revision,'take':request.take,
              'estimated_cost_usd':request.estimated_cost_usd}
        fingerprint=digest({'campaign_id':cid,'spec':{k:v for k,v in spec.items() if k!='estimated_cost_usd'}})
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM scene_jobs WHERE fingerprint=?',(fingerprint,)).fetchone()
            if old:return self.decode(old)
            if c.execute("SELECT count(*) FROM scene_jobs WHERE state IN ('queued','running')").fetchone()[0]>=12:
                raise HTTPException(409,'Queue is full. Finish or cancel pending jobs first')
            # Reserve estimates for queued work as well as all previous provider runs.
            spent=c.execute('SELECT COALESCE(SUM(estimated_cost),0) FROM provider_runs').fetchone()[0]
            waiting=c.execute("SELECT spec FROM scene_jobs WHERE state='queued'").fetchall()
            queued=sum(json.loads(r['spec'])['estimated_cost_usd'] for r in waiting)
            if spent+queued+request.estimated_cost_usd>self.s.budget_usd:
                raise HTTPException(409,'Configured estimated generation budget would be exceeded')
            jid=secrets.token_hex(8);now=time.time()
            c.execute("INSERT INTO scene_jobs VALUES(?,?,?,?,'queued',NULL,?,?)",(jid,cid,fingerprint,json.dumps(spec,ensure_ascii=False),now,now))
        self.db.log(cid,'scene_generation','Explicitly authorized Seedance scene queued. This is not a completed film or a publication.')
        return self.get(cid,jid)

    def recover(self):
        with self.db.connect() as c:
            c.execute("UPDATE scene_jobs SET state='interrupted', error='Studio restarted. Explicitly resume to reconcile the stored provider request.' WHERE state IN ('running','queued')")

    def change(self, cid, jid, action):
        self.get(cid,jid)
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if action=='cancel':
                r=c.execute("UPDATE scene_jobs SET state='cancelled',updated=? WHERE campaign_id=? AND id=? AND state='queued'",(time.time(),cid,jid))
            else:
                if not self.s.enable_paid_generation or not self.s.fal_key:
                    raise HTTPException(409,'Paid generation is disabled')
                if c.execute("SELECT count(*) FROM scene_jobs WHERE state IN ('queued','running')").fetchone()[0]>=12:
                    raise HTTPException(409,'Queue is full')
                r=c.execute("UPDATE scene_jobs SET state='queued',error=NULL,updated=? WHERE campaign_id=? AND id=? AND state IN ('failed','interrupted')",(time.time(),cid,jid))
            if r.rowcount!=1:raise HTTPException(409,'Job cannot be changed in its current state')
        return self.get(cid,jid)

    async def run_once(self):
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute("SELECT * FROM scene_jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if not row:return False
            c.execute("UPDATE scene_jobs SET state='running',updated=? WHERE id=?",(time.time(),row['id']))
        job=self.decode(row);cid,jid=job['campaign_id'],job['id'];spec=job['spec']
        try:
            folder=self.folder(cid,jid);target=folder/'scene.mp4'
            if not target.is_file():
                settings=replace(self.s,fal_model=spec['model'])
                options=BuildOptions(film_provider='fal',external_data_consent=True,
                                     estimated_cost_usd=spec['estimated_cost_usd'],provider_input=spec['input'])
                await FalFilm(settings,self.db,cid+':'+jid).generate(spec['input']['prompt'],options,target)
            await asyncio.to_thread(validate_media,target)
            with self.db.connect() as c:
                c.execute("UPDATE scene_jobs SET state='ready',error=NULL,updated=? WHERE id=?",(time.time(),jid))
            self.db.log(cid,'scene_generation','Generated scene received. Review it before using it in a finished film.')
        except asyncio.CancelledError:
            with self.db.connect() as c:c.execute("UPDATE scene_jobs SET state='interrupted',updated=? WHERE id=?",(time.time(),jid))
            raise
        except Exception as e:
            error=scrub_error(e,[self.s.fal_key])
            with self.db.connect() as c:c.execute("UPDATE scene_jobs SET state='failed',error=?,updated=? WHERE id=?",(error,time.time(),jid))
        return True

    async def worker(self, stop):
        while not stop.is_set():
            if not await self.run_once():
                try:await asyncio.wait_for(stop.wait(),timeout=1)
                except TimeoutError:pass


def register_scene_job_routes(app):
    jobs=app.state.scene_jobs
    @app.get('/api/campaigns/{cid}/scene-jobs')
    async def scene_jobs(cid:str):return {'items':jobs.list(cid),'model':SEEDANCE_MODEL,
        'configured':bool(jobs.s.fal_key and jobs.s.enable_paid_generation and jobs.s.budget_usd>0),
        'estimate_only':True,'live_verified':False}
    @app.post('/api/campaigns/{cid}/scene-jobs',status_code=202)
    async def create_job(cid:str,data:SceneGeneration):return jobs.enqueue(cid,data)
    @app.post('/api/campaigns/{cid}/scene-jobs/{jid}/resume')
    async def resume(cid:str,jid:str):return jobs.change(cid,jid,'resume')
    @app.post('/api/campaigns/{cid}/scene-jobs/{jid}/cancel')
    async def cancel(cid:str,jid:str):return jobs.change(cid,jid,'cancel')
    @app.get('/api/campaigns/{cid}/scene-jobs/{jid}/media')
    async def media(cid:str,jid:str):
        job=jobs.get(cid,jid)
        if job['state']!='ready':raise HTTPException(409,'Scene is not ready')
        file=jobs.folder(cid,jid)/'scene.mp4'
        if file.is_symlink() or not file.is_file():raise HTTPException(404,'Scene media unavailable')
        return FileResponse(file,media_type='video/mp4',filename=job['spec']['scene_id']+'.mp4')
