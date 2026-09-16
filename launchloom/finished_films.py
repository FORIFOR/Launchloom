"""Immutable final-film imports. Import is neither generation nor publication."""
from __future__ import annotations

import asyncio
import re
import secrets
import time
from pathlib import Path

from fastapi import HTTPException, Request

from .models import Brief
from .rendering import run, validate_media
from .security import file_sha, valid_id

FINAL_MEDIA = re.compile(r"finals/[a-f0-9]{32}\.mp4\Z")
MAX_FINAL_BYTES = 200 * 1024 * 1024
MAX_FINALS = 20


def initialize(db):
    with db.connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS finished_films(
          id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, media TEXT NOT NULL,
          title TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
          duration REAL NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
          ai_generated INTEGER NOT NULL, created REAL NOT NULL,
          UNIQUE(campaign_id,media))''')


def list_films(db, cid):
    with db.connect() as c:
        rows = c.execute('SELECT * FROM finished_films WHERE campaign_id=? ORDER BY created DESC,id DESC', (cid,)).fetchall()
    return [dict(row, ai_generated=bool(row['ai_generated']),
                 url=f"/artifacts/{cid}/{row['media']}") for row in rows]


def find_film(db, cid, media):
    if not FINAL_MEDIA.fullmatch(media):
        raise ValueError('Choose an imported final film from this campaign')
    with db.connect() as c:
        row = c.execute('SELECT * FROM finished_films WHERE campaign_id=? AND media=?', (cid, media)).fetchone()
    if row is None:
        raise ValueError('This final film does not belong to the campaign')
    return dict(row)


def final_path(data_dir: Path, cid: str, media: str) -> Path:
    """Do not follow symlinks, even ones pointing back inside the workspace."""
    valid_id(cid)
    if not FINAL_MEDIA.fullmatch(media):
        raise ValueError('Invalid final-film path')
    base = data_dir.resolve()
    path = base
    for part in ('campaigns', cid, *media.split('/')):
        path = path / part
        if path.is_symlink():
            raise ValueError('Symbolic links are not allowed for final films')
    if not path.resolve().is_relative_to(base):
        raise ValueError('Invalid final-film directory')
    return path


def checked_film(db, data_dir, cid, media):
    film = find_film(db, cid, media)
    path = final_path(data_dir, cid, media)
    if not path.is_file() or file_sha(path) != film['sha256']:
        raise ValueError('Final film changed or is missing. Import a new version and review it again.')
    return film, path


def prepare_file(source: Path, target: Path) -> dict:
    """Accept a finished H.264/AAC MP4/MOV, strip metadata, verify full decoding.

    No creative edits, recompression, external requests or AI detection. The
    operator declares AI provenance. Other codecs receive an actionable error.
    """
    metadata = validate_media(source)
    videos = [s for s in metadata['streams'] if s.get('codec_type') == 'video']
    audios = [s for s in metadata['streams'] if s.get('codec_type') == 'audio']
    if 'mov' not in metadata['format'].get('format_name', '').split(','):
        raise ValueError('Export a finished MP4 with H.264 video and AAC audio before importing')
    if len(videos) != 1 or len(audios) > 1:
        raise ValueError('Export one video track and at most one mixed audio track')
    video = videos[0]
    if video.get('codec_name') != 'h264' or video.get('pix_fmt') not in {'yuv420p', 'yuvj420p'}:
        raise ValueError('Export H.264, 8-bit 4:2:0 (yuv420p) MP4 for browser and publishing compatibility')
    if audios and audios[0].get('codec_name') != 'aac':
        raise ValueError('Export AAC audio in your MP4; audio is not silently removed')
    if min(video.get('width', 0), video.get('height', 0)) < 2:
        raise ValueError('Invalid final-film dimensions')
    common = ['ffmpeg', '-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov']
    run([*common, '-y', '-i', str(source), '-map', '0:v:0', '-map', '0:a:0?',
         '-map_metadata', '-1', '-map_chapters', '-1', '-c', 'copy', '-movflags', '+faststart',
         '-fs', str(MAX_FINAL_BYTES + 1), str(target)], 90)
    if target.stat().st_size > MAX_FINAL_BYTES:
        raise ValueError('The prepared final film exceeds 200 MB')
    result = validate_media(target)
    # A readable header alone does not prove the entire file is decodable.
    run([*common, '-xerror', '-threads', '2', '-i', str(target), '-map', '0:v:0',
         '-map', '0:a:0?', '-f', 'null', '-'], 120)
    if abs(float(result['format']['duration']) - float(metadata['format']['duration'])) > 0.15:
        raise ValueError('The imported film was truncated; export a smaller MP4')
    return {'duration': float(result['format']['duration']), 'width': video['width'],
            'height': video['height'], 'bytes': target.stat().st_size, 'sha256': file_sha(target)}


def register_finished_routes(app):
    db, settings = app.state.store, app.state.settings
    initialize(db)
    # One local inspection at a time; return a clear busy response rather than
    # retaining arbitrarily many large request bodies in a waiting queue.
    importing = False

    def campaign(cid):
        valid_id(cid)
        row = db.campaign(cid)
        if not row:
            raise HTTPException(404, 'Campaign not found')
        return row

    @app.get('/api/campaigns/{cid}/final-films')
    async def films(cid: str):
        campaign(cid)
        return {'items': list_films(db, cid)}

    @app.post('/api/campaigns/{cid}/final-films/media', status_code=201)
    async def import_film(cid: str, request: Request, ai_generated: bool,
                          rights_confirmed: bool = False, title: str = '完成動画'):
        nonlocal importing
        row = campaign(cid)
        title = title.strip()
        if not rights_confirmed:
            raise HTTPException(422, 'Confirm permission to use the video and audio before importing')
        if not title or len(title) > 80 or any(ord(x) < 32 for x in title):
            raise HTTPException(422, 'Use a title of 1–80 characters without control characters')
        if not any(f.approved for f in Brief.model_validate(row['brief']).features):
            raise HTTPException(422, 'Approve at least one documented product feature in the campaign first')
        if row['state'] in {'queued', 'building'}:
            raise HTTPException(409, 'Finish the active render before importing a final film')
        if len(list_films(db, cid)) >= MAX_FINALS:
            raise HTTPException(409, 'This campaign has 20 final versions. Create a new campaign.')
        if importing:
            raise HTTPException(409, 'Another final film is being inspected. Retry after it completes.')
        importing = True
        identity = secrets.token_hex(16)
        media = f'finals/{identity}.mp4'
        target = None
        source = None
        committed = False
        try:
            target = final_path(settings.data_dir, cid, media)
            target.parent.mkdir(parents=True, exist_ok=True)
            source = target.with_suffix('.upload')
            size = 0
            with source.open('xb') as f:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_FINAL_BYTES:
                        raise HTTPException(413, 'Final film exceeds 200 MB')
                    f.write(chunk)
            if not size:
                raise HTTPException(422, 'Choose a nonempty MP4 file')
            inspection = asyncio.create_task(asyncio.to_thread(prepare_file, source, target))
            try:
                facts = await asyncio.shield(inspection)
            except asyncio.CancelledError:
                # Keep ownership of temporary files until the subprocess is done.
                try: await inspection
                except Exception: pass
                raise
            except (ValueError, RuntimeError, TimeoutError) as e:
                raise HTTPException(422, str(e)[:500]) from e
            except Exception as e:
                # No local file paths or subprocess internals in unexpected errors.
                raise HTTPException(422, 'Could not inspect this film. Export H.264/AAC MP4 and retry.') from e
            with db.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                current = c.execute('SELECT state FROM campaigns WHERE id=?', (cid,)).fetchone()
                if current is None or current['state'] in {'queued', 'building'}:
                    raise HTTPException(409, 'Campaign changed during import; no final film was registered')
                uncertain = c.execute("SELECT id FROM publications WHERE campaign_id=? AND state IN ('submitting','needs_reconciliation')", (cid,)).fetchone()
                if uncertain:
                    raise HTTPException(409, 'Reconcile the pending publication before importing another final film')
                c.execute('INSERT INTO finished_films VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                          (identity, cid, media, title, facts['sha256'], facts['bytes'],
                           facts['duration'], facts['width'], facts['height'], int(ai_generated), time.time()))
                # Existing remotely submitted/scheduled posts cannot be recalled by
                # a local state change. Never rewrite their payloads or receipts.
                c.execute('UPDATE campaigns SET released=0 WHERE id=?', (cid,))
            committed = True
            db.log(cid, 'final-film', f'Final film imported: {identity}; reviewed technical metadata, publishing held.')
            return next(x for x in list_films(db, cid) if x['id'] == identity)
        finally:
            if source is not None:
                source.unlink(missing_ok=True)
            if target is not None and not committed:
                target.unlink(missing_ok=True)
            importing = False
