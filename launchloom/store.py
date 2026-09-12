from __future__ import annotations
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from .security import canonical, digest

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
              stage TEXT DEFAULT 'brief', error TEXT, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(
              id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, state TEXT NOT NULL,
              options TEXT NOT NULL, created REAL NOT NULL, started REAL, ended REAL);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON jobs(campaign_id)
              WHERE state IN ('queued','running');
            CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT NOT NULL,
              kind TEXT NOT NULL, message TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS publications(
              id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, payload TEXT NOT NULL,
              fingerprint TEXT UNIQUE NOT NULL, state TEXT NOT NULL, receipt TEXT,
              error TEXT, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS provider_runs(
              key TEXT PRIMARY KEY, provider TEXT NOT NULL, request TEXT,
              state TEXT NOT NULL, estimated_cost REAL NOT NULL DEFAULT 0, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS metrics(
              id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT NOT NULL,
              event TEXT NOT NULL, channel TEXT NOT NULL, created REAL NOT NULL);
            ''')
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
    def create_campaign(self, brief):
        cid = uuid.uuid4().hex[:16]
        with self.connect() as c:
            c.execute("INSERT INTO campaigns(id,brief,created) VALUES(?,?,?)", (cid,canonical(brief),time.time()))
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
    def enqueue(self,cid,options):
        jid=uuid.uuid4().hex[:16]
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT state,options FROM campaigns WHERE id=?",(cid,)).fetchone()
            if not row: raise ValueError("Campaign not found")
            active=c.execute("SELECT * FROM jobs WHERE campaign_id=? AND state IN ('queued','running')",(cid,)).fetchone()
            if active: return self.decode(active)
            if row['state'] == 'ready': raise ValueError("Finished campaigns are immutable. Create a new campaign to revise content.")
            if row['options'] and json.loads(row['options']) != options:
                raise ValueError("Retries must use the original build options. Clone the brief to change them.")
            c.execute("INSERT INTO jobs(id,campaign_id,state,options,created) VALUES(?,?,'queued',?,?)",(jid,cid,canonical(options),time.time()))
            c.execute("UPDATE campaigns SET state='queued',options=?,error=NULL WHERE id=?",(canonical(options),cid))
            return self.decode(c.execute("SELECT * FROM jobs WHERE id=?",(jid,)).fetchone())
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
    def record_metric(self,cid,event,channel):
        with self.connect() as c:
            c.execute("INSERT INTO metrics(campaign_id,event,channel,created) VALUES(?,?,?,?)",(cid,event,channel,time.time()))
    def metrics(self,cid):
        with self.connect() as c:
            counts={r['event']:r['n'] for r in c.execute("SELECT event,count(*) n FROM metrics WHERE campaign_id=? GROUP BY event",(cid,))}
        views=counts.get('page_view',0); clicks=counts.get('cta_click',0); conversions=counts.get('signup',0)
        return {"page_views":views,"cta_clicks":clicks,"signups":conversions,
                "conversion_rate":conversions/views if views else None,"social_impressions":None,
                "note":"Event counts, not unique people. No invented impressions or modeled conversions.",
                "recommendation":"まだ判断に必要な実測がありません。" if views<50 else "CTA到達率と登録完了を確認し、見出しを1変数ずつ比較してください（因果効果は未推定）。"}
