"""Immutable finished films, reviewed versions, and the bridge to publication.

Import never releases a campaign. Selecting a reviewed version advances an epoch;
all unsent approvals from the old epoch become stale. Remote posts are untouched.
"""
from __future__ import annotations
import asyncio
import json
import math
import os
import re
import secrets
import time
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import Field, StrictBool
from .models import StrictModel
from .security import file_sha, valid_id
from .rendering import run, validate_media

MAX_BYTES = 200 * 1024 * 1024
MEDIA_RE = re.compile(r'finals/([a-f0-9]{16})\.(mp4|jpg)\Z')


class SelectFinal(StrictModel):
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_epoch: int = Field(ge=0)
    content_reviewed: StrictBool
    rights_confirmed: StrictBool


class FinalMedia:
    def __init__(self, db, settings):
        self.db, self.s = db, settings
        with db.connect() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS final_media (
                    id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, media TEXT NOT NULL,
                    sha256 TEXT NOT NULL, title TEXT NOT NULL, width INTEGER NOT NULL,
                    height INTEGER NOT NULL, seconds REAL NOT NULL, bytes INTEGER NOT NULL,
                    ai_generated INTEGER NOT NULL, created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS final_media_campaign ON final_media(campaign_id);
                CREATE TABLE IF NOT EXISTS final_selections (
                    campaign_id TEXT NOT NULL, aspect TEXT NOT NULL, asset_id TEXT NOT NULL,
                    PRIMARY KEY(campaign_id, aspect));
                CREATE TABLE IF NOT EXISTS final_epochs (
                    campaign_id TEXT PRIMARY KEY, epoch INTEGER NOT NULL DEFAULT 0);
            ''')

    def root(self, cid: str) -> Path:
        valid_id(cid)
        if not self.db.campaign(cid):
            raise HTTPException(404, 'Campaign not found')
        base = self.s.data_dir.resolve() / 'campaigns'
        root = base / cid
        if base.is_symlink() or root.is_symlink() or root.resolve().parent != base:
            raise HTTPException(400, 'Invalid campaign directory')
        folder = root / 'finals'
        if folder.is_symlink():
            raise HTTPException(400, 'Invalid media directory')
        folder.mkdir(parents=True, exist_ok=True)
        return root

    def epoch(self, cid):
        with self.db.connect() as c:
            row = c.execute('SELECT epoch FROM final_epochs WHERE campaign_id=?', (cid,)).fetchone()
        return row['epoch'] if row else 0

    def list(self, cid):
        with self.db.connect() as c:
            rows = c.execute('''SELECT f.*, EXISTS(SELECT 1 FROM final_selections s
                WHERE s.campaign_id=f.campaign_id AND s.asset_id=f.id) AS selected
                FROM final_media f WHERE f.campaign_id=? ORDER BY f.created DESC LIMIT 100''', (cid,)).fetchall()
        return [dict(r, url=f"/artifacts/{cid}/{r['media']}",
                     poster=f"/artifacts/{cid}/finals/{r['id']}.jpg") for r in rows]

    def get(self, cid, aid):
        valid_id(aid)
        with self.db.connect() as c:
            row = c.execute('SELECT * FROM final_media WHERE campaign_id=? AND id=?', (cid, aid)).fetchone()
        if not row:
            raise HTTPException(404, 'Finished film not found')
        return dict(row)

    def path(self, cid, media):
        match = MEDIA_RE.fullmatch(media)
        if not match:
            raise HTTPException(404, 'Media is not exposed')
        self.get(cid, match[1])
        root = self.root(cid)
        path = root / media
        if path.is_symlink() or not path.is_file():
            raise HTTPException(404, 'Media is unavailable')
        return path

    def selected(self, cid):
        return [a for a in self.list(cid) if a['selected']]

    def require_selected(self, cid, media):
        match = MEDIA_RE.fullmatch(media)
        if not match or match[2] != 'mp4':
            raise HTTPException(422, 'Select a finished MP4')
        a = self.get(cid, match[1])
        with self.db.connect() as c:
            selected = c.execute('SELECT 1 FROM final_selections WHERE campaign_id=? AND asset_id=?', (cid, a['id'])).fetchone()
        if not selected:
            raise HTTPException(409, 'Review and select this finished film before preparing a post')
        if file_sha(self.path(cid, media)) != a['sha256']:
            raise HTTPException(409, 'Finished film changed on disk; import and review it again')
        return a

    def check_publication(self, p):
        if p['payload'].get('final_epoch', 0) != self.epoch(p['campaign_id']):
            raise HTTPException(409, 'A different film version was selected. Prepare a new post and approval.')
        if p['payload']['media'].startswith('finals/'):
            self.require_selected(p['campaign_id'], p['payload']['media'])

    def select(self, cid, aid, review):
        if not review.content_reviewed or not review.rights_confirmed:
            raise HTTPException(422, 'Review the actual film and confirm its rights')
        a = self.get(cid, aid)
        if review.sha256 != a['sha256'] or file_sha(self.path(cid, a['media'])) != a['sha256']:
            raise HTTPException(409, 'Film checksum changed. Import and review again.')
        aspect = 'portrait' if a['height'] > a['width'] else 'landscape'
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT epoch FROM final_epochs WHERE campaign_id=?', (cid,)).fetchone()
            epoch = row['epoch'] if row else 0
            if epoch != review.expected_epoch:
                raise HTTPException(409, 'Selection changed in another window. Reload before selecting.')
            old = c.execute('SELECT asset_id FROM final_selections WHERE campaign_id=? AND aspect=?', (cid, aspect)).fetchone()
            if old and old['asset_id'] == aid:
                return {'id': aid, 'epoch': epoch, 'unchanged': True}
            uncertain = c.execute("SELECT 1 FROM publications WHERE campaign_id=? AND state IN ('submitting','needs_reconciliation') LIMIT 1", (cid,)).fetchone()
            if uncertain:
                raise HTTPException(409, 'Reconcile the in-flight/uncertain publication before changing films')
            c.execute('INSERT INTO final_selections VALUES(?,?,?) ON CONFLICT(campaign_id,aspect) DO UPDATE SET asset_id=excluded.asset_id', (cid, aspect, aid))
            c.execute('INSERT INTO final_epochs VALUES(?,?) ON CONFLICT(campaign_id) DO UPDATE SET epoch=excluded.epoch', (cid, epoch + 1))
            c.execute("UPDATE publications SET state='superseded' WHERE campaign_id=? AND state IN ('draft','approved')", (cid,))
            c.execute('UPDATE campaigns SET released=0 WHERE id=?', (cid,))
        self.db.log(cid, 'final_review', 'Finished film selected; previous unsent approvals invalidated. Campaign held for a fresh release decision.')
        return {'id': aid, 'epoch': epoch + 1, 'unchanged': False}

    def register(self, cid, source: Path, title: str, ai_generated: bool):
        """Called only after an authorized upload or an authorized local job."""
        aid = secrets.token_hex(8)
        root = self.root(cid)
        target = root / 'finals' / (aid + '.mp4')
        poster = target.with_suffix('.jpg')
        try:
            info = normalize_final(source, target)
            run(['ffmpeg', '-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe',
                 '-i', str(target), '-frames:v', '1', '-vf', 'scale=640:-2', '-y', str(poster)], 30)
            sha = file_sha(target)
            video = next(s for s in info['streams'] if s['codec_type'] == 'video')
            seconds = float(info['format']['duration'])
            with self.db.connect() as c:
                c.execute('INSERT INTO final_media VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                          (aid, cid, f'finals/{aid}.mp4', sha, title, video['width'], video['height'],
                           seconds, target.stat().st_size, int(ai_generated), time.time()))
                c.execute('INSERT INTO events(campaign_id,kind,message,created) VALUES(?,?,?,?)',
                          (cid, 'final_import', 'Finished film imported; content review and publication approval are still required.', time.time()))
        except BaseException:
            target.unlink(missing_ok=True)
            poster.unlink(missing_ok=True)
            raise
        return self.get(cid, aid)


def normalize_final(source: Path, target: Path):
    with source.open('rb') as f:
        head = f.read(16)
    if not (head[4:8] in {b'ftyp', b'moov', b'wide', b'mdat'} or head[:4] == b'\x1aE\xdf\xa3'):
        raise ValueError('Use a real MP4, MOV or WebM video; playlists and arbitrary files are not accepted')
    info = validate_media(source)
    seconds = float(info['format']['duration'])
    if not math.isfinite(seconds) or not 0 < seconds <= 300:
        raise ValueError('Finished films must be 0–300 seconds')
    # Decode into a predictable browser/social format, remove metadata and non-media
    # tracks. No crop, added title, timing change, or creative editing is performed.
    run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-protocol_whitelist', 'file,pipe',
         '-format_whitelist', 'mov,matroska,webm', '-i', str(source), '-map', '0:v:0',
         '-map', '0:a:0?', '-sn', '-dn', '-map_metadata', '-1', '-map_chapters', '-1',
         '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1', '-c:v', 'libx264',
         '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', '-threads', '2',
         '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-t', '300',
         '-fs', str(MAX_BYTES + 1024), str(target)], 600)
    if target.stat().st_size > MAX_BYTES:
        raise ValueError('Normalized final film exceeds 200 MB')
    result = validate_media(target)
    if abs(float(result['format']['duration']) - seconds) > 0.5:
        raise ValueError('Normalized film duration differs; refusing a potentially truncated result')
    return result


def register_final_routes(app):
    service = app.state.final_media
    # One local transcode at a time. Uploads are bounded separately before waiting.
    limit = asyncio.Semaphore(1)

    @app.get('/api/campaigns/{cid}/finals')
    async def list_finals(cid: str):
        service.root(cid)
        return {'items': service.list(cid), 'epoch': service.epoch(cid)}

    @app.post('/api/campaigns/{cid}/finals/media', status_code=201)
    async def import_final(cid: str, request: Request, title: str = 'Finished film',
                           rights_confirmed: bool = False, ai_generated: bool | None = None):
        if not rights_confirmed or ai_generated is None:
            raise HTTPException(422, 'Confirm usage rights and declare whether AI-generated content is included')
        if not title.strip() or len(title) > 120 or any(ord(c) < 32 for c in title):
            raise HTTPException(422, 'Use a title of 1–120 printable characters')
        root = service.root(cid)
        # Limit stored versions to keep accidental repeat imports bounded.
        if len(service.list(cid)) >= 100:
            raise HTTPException(409, 'This campaign has reached its 100-version limit')
        temporary = root / 'finals' / ('.upload-' + secrets.token_hex(8))
        size = 0
        try:
            with temporary.open('xb') as f:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise HTTPException(413, 'Finished film exceeds 200 MB')
                    f.write(chunk)
            async with limit:
                item = await asyncio.to_thread(service.register, cid, temporary, title.strip(), ai_generated)
            return dict(item, selected=False)
        finally:
            temporary.unlink(missing_ok=True)

    @app.post('/api/campaigns/{cid}/finals/{aid}/select')
    async def select_final(cid: str, aid: str, review: SelectFinal):
        service.root(cid)
        return service.select(cid, aid, review)
