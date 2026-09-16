"""Additive, local-only handoff routes; inherits the studio's auth middleware."""
from __future__ import annotations
import json
import os
import tempfile
import threading
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response
from .production import initial_plan, validate_plan, revision, build_bundle


def register_production_routes(app):
    if getattr(app.state, "production_routes_registered", False):
        return
    app.state.production_routes_registered = True
    db, settings = app.state.store, app.state.settings
    lock = threading.Lock()

    def current(cid):
        # Avoid relying on any unchecked request value for a filesystem path.
        import re
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', cid):
            raise HTTPException(404, 'Campaign not found')
        campaign = db.campaign(cid)
        if not campaign:
            raise HTTPException(404, 'Campaign not found')
        base = (settings.data_dir / 'campaigns').resolve()
        folder = base / cid
        if folder.is_symlink() or folder.resolve().parent != base:
            raise HTTPException(400, 'Invalid campaign directory')
        path = folder / 'production-plan.json'
        if path.is_symlink():
            raise HTTPException(400, 'Invalid production file')
        plan = validate_plan(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else initial_plan(campaign['brief'])
        return path, {'plan': plan, 'revision': revision(plan), 'saved': path.exists()}

    @app.get('/production')
    async def production_page():
        return FileResponse(Path(__file__).parent / 'web' / 'production.html')

    @app.get('/api/campaigns/{cid}/production')
    async def get_production(cid: str):
        return current(cid)[1]

    @app.put('/api/campaigns/{cid}/production')
    async def save_production(cid: str, request: Request):
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 64 * 1024:
                raise HTTPException(413, 'Production plan exceeds 64 KB')
            raw.extend(chunk)
        try:
            data = json.loads(raw)
            if not isinstance(data, dict) or set(data) != {'plan', 'expected_revision'}:
                raise ValueError('Provide plan and expected_revision')
            plan = validate_plan(data['plan'])
        except (ValueError, TypeError) as e:
            raise HTTPException(422, str(e)) from e
        with lock:
            path, previous = current(cid)
            if data['expected_revision'] != previous['revision']:
                raise HTTPException(409, 'Plan changed in another window. Reload before overwriting.')
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix='.production-', dir=path.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as out:
                    json.dump(plan, out, ensure_ascii=False, indent=2)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return {'plan': plan, 'revision': revision(plan), 'saved': True}

    @app.post('/api/campaigns/{cid}/production/export')
    async def export_production(cid: str):
        _, data = current(cid)
        return Response(build_bundle(data['plan']), media_type='application/zip', headers={
            'Content-Disposition': 'attachment; filename="launchloom-production.zip"',
            'X-Production-Revision': data['revision']})
