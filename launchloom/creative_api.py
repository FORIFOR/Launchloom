"""Authenticated creative editor, durable local render jobs and explicit adoption.

The v1 production file is never overwritten by v2 saves. Jobs store an immutable
spec snapshot; missing media never triggers a provider. Single-operator only, as
with the existing studio. Startup interrupts old local jobs instead of guessing.
"""
from __future__ import annotations

import asyncio
import json
import re
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from .creative import (BrandProfile, CreativeLayer, CreativeScene, CreativeSpec,
                       creative_revision, from_production_plan)
from .creative_edits import propose_edit
from .creative_rendering import Asset, child, file_hash, media_info, preflight, render_project

HASH = re.compile(r"[a-f0-9]{64}\Z")
ID = re.compile(r"[a-z][a-z0-9_-]{0,39}\Z")
JOB_ID = re.compile(r"[a-f0-9]{32}\Z")


def initialize(db):
    with db.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS creative_specs(
          campaign_id TEXT PRIMARY KEY, spec TEXT NOT NULL, revision TEXT NOT NULL,
          production_revision TEXT NOT NULL, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS creative_jobs(
          id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, revision TEXT NOT NULL,
          production_revision TEXT NOT NULL, spec TEXT NOT NULL, state TEXT NOT NULL,
          scene_id TEXT, outputs TEXT NOT NULL, result TEXT, error TEXT,
          completed INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
          created REAL NOT NULL, ended REAL);
        CREATE UNIQUE INDEX IF NOT EXISTS creative_single_worker ON creative_jobs((1))
          WHERE state IN ('queued','running');
        CREATE TABLE IF NOT EXISTS creative_adoptions(
          job_id TEXT NOT NULL, output TEXT NOT NULL, film_id TEXT NOT NULL,
          PRIMARY KEY(job_id,output));
        ''')


async def body(request: Request, fields: set[str]) -> dict:
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 128 * 1024:
            raise HTTPException(413, "Creative request exceeds 128 KB")
        raw.extend(chunk)
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise HTTPException(422, "Invalid JSON") from exc
    if not isinstance(data, dict) or set(data) != fields:
        raise HTTPException(422, "Unexpected or missing request fields")
    return data


def _catalog(root: Path, production: dict, campaign: dict) -> dict[str, Asset]:
    """Only known local capture files and digest-checked production scene imports."""
    found = {}
    rev = production["revision"]
    if not HASH.fullmatch(rev):
        raise ValueError("Invalid production revision")
    workspace = child(root, "production-runs", rev)
    state_file = child(workspace, "execution-state.json")
    state = {}
    if state_file.is_file():
        if state_file.stat().st_size > 128 * 1024:
            raise ValueError("Production state exceeds its size limit")
        state = json.loads(state_file.read_text()).get("scenes", {})
    for scene in production["plan"]["scenes"]:
        sid = scene["id"]
        if not ID.fullmatch(sid):
            raise ValueError("Invalid scene id")
        path = child(workspace, "assets", sid + ".mp4")
        facts = state.get(sid, {})
        if path.is_file() and facts and file_hash(path) == facts.get("sha256"):
            info = media_info(path)
            generated = scene["source"] == "seedance" or facts.get("ai_generated") is True
            found[sid] = Asset(path, info["sha256"], "generated_video" if generated else "recording",
                               info["duration"], info["has_audio"], generated)
    options = campaign.get("options") or {}
    mode = options.get("capture_mode")
    capture = None
    if mode in {"url", "sample"} and (mode != "sample" or campaign["brief"].get("is_sample")):
        capture = child(root, "capture", "capture.webm")
    elif mode == "upload":
        capture = child(root, "input", "capture.bin")
    if capture and capture.is_file():
        info = media_info(capture)
        found["studio-capture"] = Asset(capture, info["sha256"], "recording", info["duration"], info["has_audio"])
    concept = child(root, "concept.mp4")
    if concept.is_file():
        info = media_info(concept)
        found["studio-concept"] = Asset(concept, info["sha256"], "generated_video", info["duration"], info["has_audio"], True)
    return found


def _derived(production: dict, campaign: dict, assets: dict[str, Asset]) -> CreativeSpec:
    spec = from_production_plan(production["plan"], campaign["brief"])
    # An existing normal-studio campaign has a real storyboard already. Use that
    # instead of inventing a new Seedance dependency for an otherwise local project.
    if not production["saved"] and campaign.get("plan"):
        options = campaign.get("options") or {}
        recording = assets.get("studio-capture")
        proof_count = sum(s["kind"] == "proof" for s in campaign["plan"]["scenes"])
        start = float(options.get("capture_start", 0))
        available = max(0, recording.duration - start) if recording else 0
        requested = float(options.get("capture_length", 0)) or available
        segment = min(5, available / max(proof_count, 1), requested / max(proof_count, 1))
        scenes, proof_index = [], 0
        for i, old in enumerate(campaign["plan"]["scenes"]):
            layers = [CreativeLayer(id="headline", kind="text", role="copy", text=old["title"])]
            claims = []
            purpose = old["kind"]
            seconds = 3.0
            if purpose == "proof":
                fi = old.get("feature_index")
                if type(fi) is int and 0 <= fi < len(campaign["brief"]["features"]):
                    if campaign["brief"]["features"][fi].get("approved"):
                        claims = [f"feature-{fi}"]
                if recording and segment >= 0.5:
                    seconds = segment
                    layers.insert(0, CreativeLayer(id="product", kind="recording", role="evidence",
                                  asset_id="studio-capture", asset_sha256=recording.sha256,
                                  start_seconds=start + proof_index * segment))
                else:
                    # The normal local/no-footage path is an explicitly conceptual
                    # title sequence, not proof or a counterfeit product recording.
                    purpose = "problem"
                proof_index += 1
            elif purpose == "hook" and assets.get("studio-concept"):
                asset = assets["studio-concept"]
                seconds = min(3, asset.duration)
                layers.insert(0, CreativeLayer(id="atmosphere", kind="generated_video", role="concept",
                              asset_id="studio-concept", asset_sha256=asset.sha256))
            scenes.append(CreativeScene(id=f"scene-{i}", purpose=purpose, title=old["title"],
                          seconds=seconds, claim_ids=claims, layers=layers))
        spec = CreativeSpec(title=spec.title, brand=spec.brand, fps=spec.fps, scenes=scenes)
    # Bind known v1 scene material. Missing assets stay missing and block rendering.
    data = spec.model_dump()
    for scene in data["scenes"]:
        for layer in scene["layers"]:
            aid = layer["asset_id"] or (scene["id"] if layer["kind"] == "generated_video" else "")
            if aid in assets and assets[aid].kind == layer["kind"]:
                layer["asset_id"] = aid
                layer["asset_sha256"] = assets[aid].sha256
    return CreativeSpec.model_validate(data)


def register_creative_routes(app, current_production):
    if getattr(app.state, "creative_registered", False):
        return
    app.state.creative_registered = True
    db, settings = app.state.store, app.state.settings
    initialize(db)
    tasks = set()
    busy = getattr(app.state, "production_execution_busy", set())
    app.state.production_execution_busy = busy
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        with db.connect() as c:
            c.execute("UPDATE creative_jobs SET state='interrupted', error='Local render interrupted. Review and render again.', ended=? WHERE state IN ('queued','running')", (time.time(),))
        async with original_lifespan(application) as state:
            try:
                yield state
            finally:
                if tasks:
                    await asyncio.gather(*list(tasks), return_exceptions=True)
    app.router.lifespan_context = lifespan

    def context(cid, include_assets=True):
        path, production = current_production(cid)
        root = path.parent
        campaign = db.campaign(cid)
        assets = _catalog(root, production, campaign) if include_assets else {}
        with db.connect() as c:
            row = c.execute("SELECT * FROM creative_specs WHERE campaign_id=?", (cid,)).fetchone()
        if row:
            spec = CreativeSpec.model_validate_json(row["spec"])
            base = row["production_revision"]
        else:
            spec = _derived(production, campaign, assets)
            base = production["revision"]
        return root, production, campaign, assets, spec, base, row is not None

    def public_job(row):
        value = dict(row)
        value.pop("spec", None)
        value["outputs"] = json.loads(value["outputs"])
        value["result"] = json.loads(value["result"]) if value["result"] else None
        if value["result"]:
            for output, item in value["result"]["outputs"].items():
                item["url"] = f"/api/campaigns/{value['campaign_id']}/creative-renders/{value['id']}/media/{output}"
        return value

    def job(cid, jid):
        current_production(cid)
        if not JOB_ID.fullmatch(jid):
            raise HTTPException(404, "Render not found")
        with db.connect() as c:
            row = c.execute("SELECT * FROM creative_jobs WHERE id=? AND campaign_id=?", (jid, cid)).fetchone()
        if row is None:
            raise HTTPException(404, "Render not found")
        return row

    def check_revision(data, spec, production, base):
        if data.get("expected_revision") != creative_revision(spec):
            raise HTTPException(409, "Creative spec changed in another window. Reload without overwriting your edits.")
        if data.get("production_revision") != production["revision"] or base != production["revision"]:
            raise HTTPException(409, "The legacy production plan changed. Explicitly reload its composition before continuing.")

    @app.get("/creative")
    async def creative_page():
        return FileResponse(Path(__file__).parent / "web" / "creative-studio.html")

    @app.get("/api/campaigns/{cid}/creative-spec")
    async def get_spec(cid: str):
        _, production, campaign, assets, spec, base, saved = context(cid)
        return {"spec": spec.model_dump(), "revision": creative_revision(spec),
                "production_revision": base, "current_production_revision": production["revision"],
                "derived": not saved, "source_changed": base != production["revision"],
                "assets": [{"id": key, "sha256": a.sha256, "kind": a.kind, "duration": a.duration,
                            "has_audio": a.has_audio, "ai_generated": a.ai_generated} for key, a in assets.items()],
                "claims": [{"id": f"feature-{i}", "title": f["title"]} for i, f in enumerate(campaign["brief"]["features"]) if f.get("approved")],
                "preflight": preflight(spec, assets),
                "renderer": "standard-720p", "external_generation": False}

    def store_spec(cid, candidate, expected, production_rev, previous_rev):
        with db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT revision FROM creative_specs WHERE campaign_id=?", (cid,)).fetchone()
            actual = row["revision"] if row else previous_rev
            if actual != expected:
                raise HTTPException(409, "Another editor saved a new version. Reload before saving.")
            if c.execute("SELECT id FROM creative_jobs WHERE campaign_id=? AND state IN ('queued','running')", (cid,)).fetchone():
                raise HTTPException(409, "This campaign is rendering. Keep your edits and save after it completes.")
            c.execute("INSERT INTO creative_specs VALUES(?,?,?,?,?) ON CONFLICT(campaign_id) DO UPDATE SET spec=excluded.spec, revision=excluded.revision, production_revision=excluded.production_revision, updated=excluded.updated",
                      (cid, candidate.model_dump_json(), creative_revision(candidate), production_rev, time.time()))
        return {"spec": candidate.model_dump(), "revision": creative_revision(candidate),
                "production_revision": production_rev, "derived": False, "saved": True}

    def validate_candidate(candidate, campaign, assets):
        approved = {f"feature-{i}" for i, f in enumerate(campaign["brief"]["features"]) if f.get("approved")}
        for scene in candidate.scenes:
            if any(key not in approved for key in scene.claim_ids):
                raise HTTPException(422, "Only this campaign's approved feature ids may be referenced")
            if scene.purpose == "proof" and not scene.claim_ids:
                raise HTTPException(422, "Link a proof scene to an approved feature")
            for layer in scene.layers:
                asset = assets.get(layer.asset_id)
                if asset and (asset.kind != layer.kind or (layer.role == "evidence" and asset.ai_generated)):
                    raise HTTPException(422, "Media provenance cannot be changed by editing the spec")
                if asset and layer.asset_sha256 and layer.asset_sha256 != asset.sha256:
                    raise HTTPException(409, "Media changed. Select the current asset and review it again.")

    @app.put("/api/campaigns/{cid}/creative-spec")
    async def save(cid: str, request: Request):
        data = await body(request, {"spec", "expected_revision", "production_revision"})
        _, production, campaign, assets, previous, base, _ = context(cid)
        check_revision(data, previous, production, base)
        if cid in busy:
            raise HTTPException(409, "Another production action is running")
        candidate = CreativeSpec.model_validate(data["spec"])
        validate_candidate(candidate, campaign, assets)
        result = store_spec(cid, candidate, data["expected_revision"], base, creative_revision(previous))
        db.log(cid, "creative", "Saved operator-edited creative spec; existing finished films and posts are unchanged.")
        return result

    @app.post("/api/campaigns/{cid}/creative-spec/reset")
    async def reset(cid: str, request: Request):
        data = await body(request, {"expected_revision", "production_revision", "confirmed"})
        _, production, campaign, assets, previous, _, _ = context(cid)
        if data["confirmed"] is not True or cid in busy:
            raise HTTPException(409, "Confirm replacement when no production action is running")
        if data["production_revision"] != production["revision"]:
            raise HTTPException(409, "The production plan changed again. Reload first.")
        candidate = _derived(production, campaign, assets)
        return store_spec(cid, candidate, data["expected_revision"], production["revision"], creative_revision(previous))

    @app.post("/api/campaigns/{cid}/creative-spec/propose-edit")
    async def edit(cid: str, request: Request):
        data = await body(request, {"expected_revision", "production_revision", "scene_id", "instruction", "output"})
        _, production, _, _, spec, base, _ = context(cid)
        check_revision(data, spec, production, base)
        if not isinstance(data["instruction"], str):
            raise HTTPException(422, "Instruction must be text")
        return propose_edit(spec, data["scene_id"], data["instruction"], data["output"])

    async def work(cid, jid, spec, assets, root, scene_id, outputs):
        def progress(done, total):
            with db.connect() as c:
                c.execute("UPDATE creative_jobs SET completed=?,total=? WHERE id=?", (done, total, jid))
        future = None
        try:
            with db.connect() as c:
                c.execute("UPDATE creative_jobs SET state='running' WHERE id=?", (jid,))
            cache = child(root, "creative-cache")
            destination = child(root, "creative-renders", jid)
            future = asyncio.create_task(asyncio.to_thread(render_project, spec, assets, cache, destination,
                                         scene_id=scene_id, outputs=outputs, progress=progress))
            result = await asyncio.shield(future)
            from .creative_quality import inspect_render
            def inspect_outputs():
                return {output: inspect_render(spec, child(destination, output + ".mp4"), output,
                                              info["sha256"], scene_id)
                        for output, info in result["outputs"].items()}
            future = asyncio.create_task(asyncio.to_thread(inspect_outputs))
            result["quality_review"] = await asyncio.shield(future)
            with db.connect() as c:
                c.execute("UPDATE creative_jobs SET state='ready',result=?,ended=? WHERE id=?",
                          (json.dumps(result), time.time(), jid))
        except asyncio.CancelledError:
            if future:
                try: await future
                except Exception: pass
            with db.connect() as c:
                c.execute("UPDATE creative_jobs SET state='interrupted',error='Local rendering interrupted; review and retry.',ended=? WHERE id=?", (time.time(), jid))
            raise
        except Exception as exc:
            message = str(exc)[:1200] if isinstance(exc, ValueError) else "Local render failed. No generation or publication was performed."
            with db.connect() as c:
                c.execute("UPDATE creative_jobs SET state='failed',error=?,ended=? WHERE id=?", (message, time.time(), jid))
        finally:
            busy.discard(cid)

    @app.post("/api/campaigns/{cid}/creative-renders", status_code=202)
    async def start_render(cid: str, request: Request):
        data = await body(request, {"expected_revision", "production_revision", "scene_id", "outputs", "rights_confirmed"})
        root, production, _, assets, spec, base, saved = context(cid)
        check_revision(data, spec, production, base)
        if not saved:
            raise HTTPException(409, "Save the creative composition before rendering")
        if data["rights_confirmed"] is not True:
            raise HTTPException(422, "Confirm permission to use the video, audio and copy")
        outputs, sid = data["outputs"], data["scene_id"]
        if not isinstance(outputs, list) or not outputs or len(outputs) > 2 or any(not isinstance(o, str) or o not in spec.outputs for o in outputs) or len(set(outputs)) != len(outputs):
            raise HTTPException(422, "Choose unique enabled outputs")
        if sid is not None and (not isinstance(sid, str) or sid not in {s.id for s in spec.scenes}):
            raise HTTPException(422, "Choose an existing scene or the complete film")
        blockers = preflight(spec, assets, sid)
        if blockers:
            raise HTTPException(422, blockers)
        jid = secrets.token_hex(16)
        with db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            if cid in busy or c.execute("SELECT id FROM creative_jobs WHERE state IN ('queued','running')").fetchone():
                raise HTTPException(409, "Another local render is running")
            if c.execute("SELECT count(*) FROM creative_jobs WHERE campaign_id=?", (cid,)).fetchone()[0] >= 30:
                raise HTTPException(409, "This campaign has 30 render attempts; create a new campaign before continuing")
            state = c.execute("SELECT state FROM campaigns WHERE id=?", (cid,)).fetchone()[0]
            if state in {"queued", "building"}:
                raise HTTPException(409, "Finish the existing studio render first")
            c.execute("INSERT INTO creative_jobs(id,campaign_id,revision,production_revision,spec,state,scene_id,outputs,created) VALUES(?,?,?,?,?,'queued',?,?,?)",
                      (jid, cid, creative_revision(spec), base, spec.model_dump_json(), sid, json.dumps(outputs), time.time()))
        busy.add(cid)
        task = asyncio.create_task(work(cid, jid, spec, assets, root, sid, outputs))
        tasks.add(task); task.add_done_callback(tasks.discard)
        return public_job(job(cid, jid))

    @app.get("/api/campaigns/{cid}/creative-renders")
    async def list_renders(cid: str):
        current_production(cid)
        with db.connect() as c:
            rows = c.execute("SELECT * FROM creative_jobs WHERE campaign_id=? ORDER BY created DESC LIMIT 30", (cid,)).fetchall()
        return {"items": [public_job(row) for row in rows]}

    @app.get("/api/campaigns/{cid}/creative-renders/{jid}")
    async def get_render(cid: str, jid: str):
        return public_job(job(cid, jid))

    def rendered(cid, jid, output):
        row = job(cid, jid)
        if row["state"] != "ready" or output not in json.loads(row["outputs"]):
            raise HTTPException(409, "This render is not ready for the requested output")
        root = current_production(cid)[0].parent
        path = child(root, "creative-renders", jid, output + ".mp4")
        info = json.loads(row["result"])["outputs"][output]
        if not path.is_file() or file_hash(path) != info["sha256"]:
            raise HTTPException(409, "Rendered film changed or is missing; render a new version")
        return row, path

    @app.get("/api/campaigns/{cid}/creative-renders/{jid}/media/{output}")
    async def preview(cid: str, jid: str, output: str):
        if output not in {"landscape", "portrait"}:
            raise HTTPException(404, "Output not found")
        _, path = rendered(cid, jid, output)
        return FileResponse(path, media_type="video/mp4")

    @app.post("/api/campaigns/{cid}/creative-renders/{jid}/adopt")
    async def adopt(cid: str, jid: str, request: Request):
        data = await body(request, {"output", "expected_revision", "rights_confirmed", "content_reviewed"})
        if data["rights_confirmed"] is not True or data["content_reviewed"] is not True:
            raise HTTPException(422, "Review the exact film and confirm usage rights before adopting it")
        if not isinstance(data["output"], str) or data["output"] not in {"landscape", "portrait"}:
            raise HTTPException(422, "Choose a rendered output")
        row, source = rendered(cid, jid, data["output"])
        _, production, campaign, _, spec, base, _ = context(cid)
        if row["scene_id"] is not None:
            raise HTTPException(422, "A scene preview is not a complete film")
        if row["revision"] != data["expected_revision"] or row["revision"] != creative_revision(spec) or base != production["revision"]:
            raise HTTPException(409, "This preview is from an older composition; render the saved version before adopting")
        if cid in busy:
            raise HTTPException(409, "Another production action is running")
        from .finished_films import initialize as init_films, final_path, prepare_file, list_films, checked_film, MAX_FINALS
        init_films(db)
        with db.connect() as c:
            existing = c.execute("SELECT film_id FROM creative_adoptions WHERE job_id=? AND output=?", (jid, data["output"])).fetchone()
        if existing:
            film = next(x for x in list_films(db, cid) if x["id"] == existing["film_id"])
            checked_film(db, settings.data_dir, cid, film["media"])
            return film
        identity = secrets.token_hex(16)
        target = final_path(settings.data_dir, cid, f"finals/{identity}.mp4")
        target.parent.mkdir(parents=True, exist_ok=True)
        busy.add(cid)
        committed = False
        inspection = None
        try:
            inspection = asyncio.create_task(asyncio.to_thread(prepare_file, source, target))
            facts = await asyncio.shield(inspection)
            if file_hash(source) != json.loads(row["result"])["outputs"][data["output"]]["sha256"]:
                raise HTTPException(409, "Preview media changed during adoption")
            with db.connect() as c:
                c.execute("BEGIN IMMEDIATE")
                live = c.execute("SELECT state FROM campaigns WHERE id=?", (cid,)).fetchone()
                now = c.execute("SELECT revision FROM creative_specs WHERE campaign_id=?", (cid,)).fetchone()
                if not live or live["state"] in {"queued", "building"} or not now or now["revision"] != row["revision"]:
                    raise HTTPException(409, "Campaign changed while preparing the final film")
                if c.execute("SELECT id FROM publications WHERE campaign_id=? AND state IN ('submitting','needs_reconciliation')", (cid,)).fetchone():
                    raise HTTPException(409, "Reconcile the uncertain publication before adopting another film")
                if not any(f.get("approved") for f in campaign["brief"]["features"]):
                    raise HTTPException(422, "Approve a documented product feature before adopting a final film")
                if c.execute("SELECT count(*) FROM finished_films WHERE campaign_id=?", (cid,)).fetchone()[0] >= MAX_FINALS:
                    raise HTTPException(409, "Final-film version limit reached")
                title = f"{spec.title[:45]} / {data['output']}"
                generated = any(x.kind == "generated_video" for s in spec.scenes for x in s.layers)
                c.execute("INSERT INTO finished_films VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                          (identity, cid, f"finals/{identity}.mp4", title, facts["sha256"], facts["bytes"],
                           facts["duration"], facts["width"], facts["height"], int(generated), time.time()))
                c.execute("INSERT INTO creative_adoptions VALUES(?,?,?)", (jid, data["output"], identity))
                c.execute("UPDATE campaigns SET released=0 WHERE id=?", (cid,))
                c.execute("INSERT INTO events(campaign_id,kind,message,created) VALUES(?,?,?,?)",
                          (cid, "creative", f"Adopted local render {jid} / {data['output']}; publishing held.", time.time()))
            committed = True
            return next(x for x in list_films(db, cid) if x["id"] == identity)
        except asyncio.CancelledError:
            if inspection:
                try: await inspection
                except Exception: pass
            raise
        finally:
            if not committed: target.unlink(missing_ok=True)
            busy.discard(cid)

    from .creative_workflow_api import register_workflow_routes
    register_workflow_routes(app, context=context, job=job, rendered=rendered,
        check_revision=check_revision, validate_candidate=validate_candidate, body=body, busy=busy)
