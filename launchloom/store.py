from __future__ import annotations
import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from .security import canonical, digest

class CreationConflict(ValueError):
    """An operation key was already used for different input."""

class Store:
    """SQLite is the source of truth. One render worker; no in-memory-only job queue."""
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS campaigns(
              id TEXT PRIMARY KEY, brief TEXT NOT NULL, options TEXT, plan TEXT,
              state TEXT NOT NULL DEFAULT 'draft', progress INTEGER DEFAULT 0,
              stage TEXT DEFAULT 'brief', error TEXT, created REAL NOT NULL,
              plan_approved INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS jobs(
              id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, state TEXT NOT NULL,
              options TEXT NOT NULL, created REAL NOT NULL, started REAL, ended REAL);
            CREATE TABLE IF NOT EXISTS campaign_requests(
              key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
              campaign_id TEXT NOT NULL REFERENCES campaigns(id));
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON jobs(campaign_id)
              WHERE state IN ('queued','running');
            CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT NOT NULL,
              kind TEXT NOT NULL, message TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS publications(
              id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, payload TEXT NOT NULL,
              fingerprint TEXT UNIQUE NOT NULL, state TEXT NOT NULL, receipt TEXT,
              error TEXT, created REAL NOT NULL,
              remote_state TEXT, remote_url TEXT, checked REAL);
            CREATE TABLE IF NOT EXISTS provider_runs(
              key TEXT PRIMARY KEY, provider TEXT NOT NULL, request TEXT,
              state TEXT NOT NULL, estimated_cost REAL NOT NULL DEFAULT 0, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS metrics(
              id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT NOT NULL,
              event TEXT NOT NULL, channel TEXT NOT NULL, created REAL NOT NULL,
              dedupe_key TEXT);
            ''')
            # Older databases predate the review gate and revision counter.
            existing={r['name'] for r in c.execute('PRAGMA table_info(campaigns)')}
            for name,declaration in (('plan_approved','INTEGER NOT NULL DEFAULT 0'),('revision','INTEGER NOT NULL DEFAULT 0'),
                                     ('released','INTEGER NOT NULL DEFAULT 0')):
                if name not in existing: c.execute(f'ALTER TABLE campaigns ADD COLUMN {name} {declaration}')
            existing={r['name'] for r in c.execute('PRAGMA table_info(publications)')}
            for name,declaration in (('remote_state','TEXT'),('remote_url','TEXT'),('checked','REAL')):
                if name not in existing: c.execute(f'ALTER TABLE publications ADD COLUMN {name} {declaration}')
            if 'dedupe_key' not in {r['name'] for r in c.execute('PRAGMA table_info(metrics)')}:
                c.execute('ALTER TABLE metrics ADD COLUMN dedupe_key TEXT')
            # Indexes come after migration: on an existing database the column
            # this one covers does not exist until the ALTER above has run.
            c.execute('CREATE UNIQUE INDEX IF NOT EXISTS one_event_per_key ON metrics(dedupe_key) WHERE dedupe_key IS NOT NULL')
    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout=15000")
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()
    @staticmethod
    def decode(row):
        if row is None: return None
        d = dict(row)
        for k in ("brief", "options", "plan", "payload", "receipt", "request"):
            if k in d and d[k]: d[k] = json.loads(d[k])
        return d
    def campaign(self, cid):
        with self.connect() as c: return self.decode(c.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone())
    def campaigns(self):
        with self.connect() as c: return [self.decode(r) for r in c.execute("SELECT * FROM campaigns ORDER BY created DESC LIMIT 100")]
    def create_campaign(self, brief, *, idempotency_key=None, options=None):
        """Persist one creation intent, optionally with its first job, atomically.

        Keys survive process restarts for the lifetime of this local database.
        Replaying a creation never retries a failed job or changes saved edits.
        """
        if idempotency_key is not None and not re.fullmatch(r'[A-Za-z0-9._:-]{8,128}', idempotency_key):
            raise ValueError('Idempotency-Key must be 8–128 ASCII letters, digits, dot, colon, underscore or hyphen')
        fingerprint = digest({'brief':brief, 'options':options})
        cid = uuid.uuid4().hex[:16]
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if idempotency_key is not None:
                old=c.execute('SELECT * FROM campaign_requests WHERE key=?',(idempotency_key,)).fetchone()
                if old:
                    if old['fingerprint'] != fingerprint:
                        raise CreationConflict('Idempotency-Key already used for different input. Resume the original campaign or use a new key for a new intent.')
                    return self.decode(c.execute('SELECT * FROM campaigns WHERE id=?',(old['campaign_id'],)).fetchone())
            c.execute("INSERT INTO campaigns(id,brief,created) VALUES(?,?,?)", (cid,canonical(brief),time.time()))
            if options is not None:
                c.execute("INSERT INTO jobs(id,campaign_id,state,options,created) VALUES(?,?,'queued',?,?)",
                          (uuid.uuid4().hex[:16],cid,canonical(options),time.time()))
                c.execute("UPDATE campaigns SET state='queued',options=? WHERE id=?",(canonical(options),cid))
            if idempotency_key is not None:
                c.execute('INSERT INTO campaign_requests VALUES(?,?,?)',(idempotency_key,fingerprint,cid))
        return self.campaign(cid)
    def progress(self, cid, stage, percent, state="building", error=None, plan=None):
        with self.connect() as c:
            c.execute("UPDATE campaigns SET state=?,stage=?,progress=?,error=? WHERE id=?", (state,stage,percent,error,cid))
            if plan: c.execute("UPDATE campaigns SET plan=? WHERE id=?", (canonical(plan),cid))
    def log(self, cid, kind, message):
        with self.connect() as c:
            c.execute("INSERT INTO events(campaign_id,kind,message,created) VALUES(?,?,?,?)",(cid,kind,message,time.time()))
    def events(self,cid):
        with self.connect() as c: return [dict(r) for r in c.execute("SELECT * FROM events WHERE campaign_id=? ORDER BY id DESC LIMIT 80",(cid,))]
    def enqueue(self,cid,options,revision=False):
        """Queue one build. A revision re-renders an existing campaign from the
        material it already has; it never changes the build options, so nothing is
        re-recorded and no paid generation is repeated."""
        jid=uuid.uuid4().hex[:16]
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT state,options FROM campaigns WHERE id=?",(cid,)).fetchone()
            if not row: raise ValueError("Campaign not found")
            if row['options'] and json.loads(row['options']) != options:
                raise ValueError("Retries must use the original build options. Clone the brief to change them.")
            active=c.execute("SELECT * FROM jobs WHERE campaign_id=? AND state IN ('queued','running')",(cid,)).fetchone()
            if active: return self.decode(active)
            if row['state']=='ready' and not revision:
                raise ValueError("This campaign is finished. Revise it from the review panel, or create a new campaign to change the brief.")
            if revision and row['state'] not in {'ready','awaiting_review'}:
                raise ValueError("Only a finished or reviewable campaign can be revised")
            c.execute("INSERT INTO jobs(id,campaign_id,state,options,created) VALUES(?,?,'queued',?,?)",(jid,cid,canonical(options),time.time()))
            c.execute("UPDATE campaigns SET state='queued',options=?,error=NULL WHERE id=?",(canonical(options),cid))
            # Resuming a reviewed campaign is the first render, not a revision.
            if revision and row['state']=='ready': c.execute("UPDATE campaigns SET revision=revision+1 WHERE id=?",(cid,))
            return self.decode(c.execute("SELECT * FROM jobs WHERE id=?",(jid,)).fetchone())

    def save_plan(self,cid,plan,approved=None):
        """Store the storyboard the next render must use."""
        with self.connect() as c:
            c.execute("UPDATE campaigns SET plan=? WHERE id=?",(canonical(plan),cid))
            if approved is not None: c.execute("UPDATE campaigns SET plan_approved=? WHERE id=?",(1 if approved else 0,cid))
        return self.campaign(cid)
    def claim_job(self):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            r=c.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if not r: return None
            c.execute("UPDATE jobs SET state='running',started=? WHERE id=?",(time.time(),r['id']))
            return self.decode(r)
    def finish_job(self,jid,state):
        with self.connect() as c: c.execute("UPDATE jobs SET state=?,ended=? WHERE id=?",(state,time.time(),jid))
    def recover(self):
        # Do not automatically repeat a paid generation or an uncertain external publish.
        with self.connect() as c:
            c.execute("UPDATE campaigns SET state='interrupted',error='Worker interrupted. Review provider status, then retry.' WHERE id IN (SELECT campaign_id FROM jobs WHERE state='running')")
            c.execute("UPDATE jobs SET state='interrupted' WHERE state='running'")
            c.execute("UPDATE publications SET state='needs_reconciliation',error='Process stopped during external submission. Check Postiz before repeating.' WHERE state='submitting'")
            c.execute("UPDATE provider_runs SET state='needs_reconciliation' WHERE state='submitting'")
    def publication(self,pid):
        with self.connect() as c: return self.decode(c.execute("SELECT * FROM publications WHERE id=?",(pid,)).fetchone())
    def publications(self,cid):
        with self.connect() as c: return [self.decode(r) for r in c.execute("SELECT * FROM publications WHERE campaign_id=? ORDER BY created DESC",(cid,))]
    def create_publication(self,cid,payload):
        fingerprint=digest({"campaign_id":cid,"payload":payload})
        pid=uuid.uuid4().hex[:16]
        with self.connect() as c:
            c.execute("INSERT OR IGNORE INTO publications(id,campaign_id,payload,fingerprint,state,created) VALUES(?,?,?,?,'draft',?)",(pid,cid,canonical(payload),fingerprint,time.time()))
            return self.decode(c.execute("SELECT * FROM publications WHERE fingerprint=?",(fingerprint,)).fetchone())
    def approve(self,pid,fingerprint):
        with self.connect() as c:
            r=c.execute("UPDATE publications SET state='approved' WHERE id=? AND fingerprint=? AND state IN ('draft','approved')",(pid,fingerprint))
            if r.rowcount != 1: raise ValueError("Approval is stale, already submitted, or invalid")
        return self.publication(pid)
    def claim_publication(self,pid):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            r=c.execute("UPDATE publications SET state='submitting' WHERE id=? AND state='approved'",(pid,))
            if r.rowcount != 1: raise ValueError("Publication is not approved or is already being submitted")
        return self.publication(pid)
    def release_campaign(self,cid,released=True):
        """An explicit, separate act from finishing the film: the operator says this
        campaign may leave the machine."""
        with self.connect() as c:
            c.execute("UPDATE campaigns SET released=? WHERE id=?",(1 if released else 0,cid))
        return self.campaign(cid)

    def record_remote_state(self,pid,state,url=None):
        """What the platform says, kept apart from what our submission said."""
        with self.connect() as c:
            c.execute("UPDATE publications SET remote_state=?,remote_url=?,checked=? WHERE id=?",(state,url,time.time(),pid))

    def channel_schedule(self,cid,channel):
        """Times already claimed on one channel, for spacing and daily limits."""
        entries=[]
        for p in self.publications(cid):
            if p['payload'].get('channel')!=channel or p['state'] in {'draft','cancelled'}:continue
            entries.append({'id':p['id'],'state':p['state'],'at':p['payload'].get('schedule_at') or '','created':p['created']})
        return entries

    def publication_result(self,pid,state,receipt=None,error=None):
        with self.connect() as c:
            c.execute("UPDATE publications SET state=?,receipt=?,error=? WHERE id=?",(state,canonical(receipt) if receipt else None,error,pid))
    def provider_run(self,key):
        with self.connect() as c: return self.decode(c.execute("SELECT * FROM provider_runs WHERE key=?",(key,)).fetchone())
    def reserve_provider(self,key,provider,cost,budget):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            old=c.execute("SELECT * FROM provider_runs WHERE key=?",(key,)).fetchone()
            if old:return self.decode(old)
            spent=c.execute("SELECT COALESCE(SUM(estimated_cost),0) FROM provider_runs").fetchone()[0]
            if spent+cost>budget: raise ValueError("Configured estimated generation budget would be exceeded")
            c.execute("INSERT INTO provider_runs(key,provider,state,estimated_cost,created) VALUES(?,?,'submitting',?,?)",(key,provider,cost,time.time()))
        return None
    def provider_update(self,key,state,request=None):
        with self.connect() as c:
            if request is None:c.execute("UPDATE provider_runs SET state=? WHERE key=?",(state,key))
            else:c.execute("UPDATE provider_runs SET state=?,request=? WHERE key=?",(state,canonical(request),key))
    def record_metric(self,cid,event,channel,dedupe_key=None):
        """Returns False when this exact event was already counted."""
        with self.connect() as c:
            cursor=c.execute("INSERT OR IGNORE INTO metrics(campaign_id,event,channel,created,dedupe_key) VALUES(?,?,?,?,?)",
                             (cid,event,channel,time.time(),dedupe_key))
            return cursor.rowcount==1
    def metrics(self,cid):
        with self.connect() as c:
            counts={r['event']:r['n'] for r in c.execute("SELECT event,count(*) n FROM metrics WHERE campaign_id=? GROUP BY event",(cid,))}
        views=counts.get('page_view',0); clicks=counts.get('cta_click',0); conversions=counts.get('signup',0)
        return {"page_views":views,"cta_clicks":clicks,"signups":conversions,
                "conversion_rate":conversions/views if views else None,"social_impressions":None,
                "note":"Event counts, not unique people. No invented impressions or modeled conversions.",
                "recommendation":"まだ判断に必要な実測がありません。" if views<50 else "CTA到達率と登録完了を確認し、見出しを1変数ずつ比較してください（因果効果は未推定）。"}
