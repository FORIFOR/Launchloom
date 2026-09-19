"""Native-app integration tests; external providers and publishing remain disabled."""
import shutil
import threading
import time

import pytest
from fastapi.testclient import TestClient

from launchloom.config import Settings
from launchloom.server import create_app
from launchloom.creative import BrandProfile, CreativeLayer, CreativeScene, CreativeSpec

TOKEN = "creative-integration-local-token-1234"
BRIEF = {"name": "Type study", "tagline": "Make it seen.", "audience": "Designers",
         "features": [{"title": "Typography study", "detail": "A local composition exercise, not a product demonstration.",
                       "evidence": "Operator-authored fixture used only in tests.", "approved": True}],
         "channels": ["x"], "language": "en"}


def fixture_spec():
    return CreativeSpec(title="Typography study", brand=BrandProfile(name="Launchloom"), scenes=[
        CreativeScene(id="opening", purpose="hook", seconds=.6,
            layers=[CreativeLayer(id="headline", kind="text", role="copy", text="Make the moment matter.")]),
        CreativeScene(id="closing", purpose="cta", seconds=.6,
            layers=[CreativeLayer(id="headline", kind="text", role="copy", text="Keep what works.")])]).model_dump()


@pytest.fixture
def studio(tmp_path):
    settings = Settings(data_dir=tmp_path, token=TOKEN, enable_paid_generation=False, enable_live_publish=False)
    app = create_app(settings, run_worker=False)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + TOKEN
        cid = client.post("/api/campaigns", json=BRIEF).json()["id"]
        yield client, app, cid, tmp_path


def get(client, cid):
    response = client.get(f"/api/campaigns/{cid}/creative-spec")
    assert response.status_code == 200, response.text
    return response.json()


def save(client, cid, spec=None, previous=None):
    previous = previous or get(client, cid)
    return client.put(f"/api/campaigns/{cid}/creative-spec", json={
        "spec": spec or fixture_spec(), "expected_revision": previous["revision"],
        "production_revision": previous["production_revision"]})


def render(client, cid, scene_id=None):
    current = get(client, cid)
    response = client.post(f"/api/campaigns/{cid}/creative-renders", json={
        "expected_revision": current["revision"], "production_revision": current["production_revision"],
        "scene_id": scene_id, "outputs": ["landscape"], "rights_confirmed": True})
    assert response.status_code == 202, response.text
    jid = response.json()["id"]
    for _ in range(300):
        job = client.get(f"/api/campaigns/{cid}/creative-renders/{jid}").json()
        if job["state"] not in {"queued", "running"}:
            assert job["state"] == "ready", job
            return job
        time.sleep(.05)
    pytest.fail("Local fixture render did not complete")


def test_auth_csrf_and_size_limit(studio):
    client, app, cid, root = studio
    auth = client.headers.pop("Authorization")
    assert client.get(f"/api/campaigns/{cid}/creative-spec").status_code == 401
    assert client.put(f"/api/campaigns/{cid}/creative-spec", json={}).status_code == 401
    client.headers["Authorization"] = auth
    assert client.put(f"/api/campaigns/{cid}/creative-spec", json={}, headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert client.put(f"/api/campaigns/{cid}/creative-spec", content=b"x" * (128*1024+1)).status_code == 413


def test_save_conflict_keeps_legacy_and_approved_films_unchanged(studio):
    client, app, cid, root = studio
    before = get(client, cid)
    assert before["derived"] is True
    legacy = client.get(f"/api/campaigns/{cid}/production").json()
    app.state.store.release_campaign(cid, True)
    assert save(client, cid, previous=before).status_code == 200
    assert save(client, cid, previous=before).status_code == 409
    assert get(client, cid)["derived"] is False
    assert client.get(f"/api/campaigns/{cid}/production").json() == legacy
    assert app.state.store.campaign(cid)["released"] == 1
    assert app.state.store.publications(cid) == []


def test_unknown_fields_and_foreign_claims_rejected(studio):
    client, _, cid, _ = studio
    bad = fixture_spec(); bad["api_key"] = "not-a-real-key"
    assert save(client, cid, bad).status_code == 422
    bad = fixture_spec(); bad["scenes"][0]["claim_ids"] = ["feature-7"]
    assert save(client, cid, bad).status_code == 422


def test_legacy_changes_require_explicit_reset(studio):
    client, _, cid, _ = studio
    assert save(client, cid).status_code == 200
    legacy = client.get(f"/api/campaigns/{cid}/production").json()
    legacy["plan"]["title"] = "Changed original"
    assert client.put(f"/api/campaigns/{cid}/production", json={"plan": legacy["plan"], "expected_revision": legacy["revision"]}).status_code == 200
    current = get(client, cid)
    assert current["source_changed"] and current["spec"]["title"] == "Typography study"
    assert save(client, cid, previous=current).status_code == 409
    reset = client.post(f"/api/campaigns/{cid}/creative-spec/reset", json={
        "expected_revision": current["revision"], "production_revision": current["current_production_revision"], "confirmed": True})
    assert reset.status_code == 200, reset.text
    assert get(client, cid)["source_changed"] is False


def test_edit_proposal_is_not_saved_or_executed(studio):
    client, _, cid, _ = studio
    assert save(client, cid).status_code == 200
    before = get(client, cid)
    response = client.post(f"/api/campaigns/{cid}/creative-spec/propose-edit", json={
        "expected_revision": before["revision"], "production_revision": before["production_revision"],
        "scene_id": "opening", "instruction": "文字を上へ", "output": "portrait"})
    assert response.status_code == 200, response.text
    assert response.json()["saved"] is False
    assert response.json()["spec"]["scenes"][0]["layouts"]["portrait"]["y"] == pytest.approx(.70)
    assert get(client, cid)["revision"] == before["revision"]


def test_local_worker_excludes_duplicate_renders_and_legacy_saves(studio, monkeypatch):
    client, _, cid, _ = studio
    assert save(client, cid).status_code == 200
    ready, release = threading.Event(), threading.Event()
    def blocked(*args, **kwargs):
        ready.set(); release.wait(10)
        return {"outputs": {}, "scenes": []}
    monkeypatch.setattr("launchloom.creative_api.render_project", blocked)
    state = get(client, cid)
    payload = {"expected_revision": state["revision"], "production_revision": state["production_revision"],
               "scene_id": None, "outputs": ["landscape"], "rights_confirmed": True}
    try:
        assert client.post(f"/api/campaigns/{cid}/creative-renders", json=payload).status_code == 202
        assert ready.wait(3)
        assert client.post(f"/api/campaigns/{cid}/creative-renders", json=payload).status_code == 409
        assert save(client, cid).status_code == 409
        legacy = client.get(f"/api/campaigns/{cid}/production").json()
        assert client.put(f"/api/campaigns/{cid}/production", json={"plan": legacy["plan"], "expected_revision": legacy["revision"]}).status_code == 409
    finally:
        release.set()


media = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required")


@media
def test_real_render_range_preview_and_idempotent_adoption(studio):
    client, app, cid, root = studio
    assert save(client, cid).status_code == 200
    app.state.store.release_campaign(cid, True)
    result = render(client, cid)
    assert app.state.store.campaign(cid)["released"] == 1  # preview is not adoption
    url = result["result"]["outputs"]["landscape"]["url"]
    media_response = client.get(url, headers={"Range": "bytes=0-100"})
    assert media_response.status_code == 206 and len(media_response.content) == 101
    args = {"expected_revision": result["revision"], "output": "landscape", "rights_confirmed": True, "content_reviewed": True}
    endpoint = f"/api/campaigns/{cid}/creative-renders/{result['id']}/adopt"
    first = client.post(endpoint, json=args)
    assert first.status_code == 200, first.text
    second = client.post(endpoint, json=args)
    assert first.json()["id"] == second.json()["id"]
    assert len(client.get(f"/api/campaigns/{cid}/final-films").json()["items"]) == 1
    assert app.state.store.campaign(cid)["released"] == 0
    assert app.state.store.publications(cid) == []


@media
def test_changed_media_and_scene_previews_cannot_be_adopted(studio):
    client, _, cid, root = studio
    assert save(client, cid).status_code == 200
    result = render(client, cid, scene_id="opening")
    endpoint = f"/api/campaigns/{cid}/creative-renders/{result['id']}/adopt"
    args = {"expected_revision": result["revision"], "output": "landscape", "rights_confirmed": True, "content_reviewed": True}
    assert client.post(endpoint, json=args).status_code == 422
    (root / "campaigns" / cid / "creative-renders" / result["id"] / "landscape.mp4").write_bytes(b"tampered")
    assert client.get(result["result"]["outputs"]["landscape"]["url"]).status_code == 409


@media
def test_stale_revision_and_uncertain_publication_block_adoption(studio):
    client, app, cid, root = studio
    assert save(client, cid).status_code == 200
    result = render(client, cid)
    endpoint = f"/api/campaigns/{cid}/creative-renders/{result['id']}/adopt"
    args = {"expected_revision": result["revision"], "output": "landscape", "rights_confirmed": True, "content_reviewed": True}
    post = app.state.store.create_publication(cid, {"content": "test only"})
    app.state.store.publication_result(post["id"], "needs_reconciliation")
    assert client.post(endpoint, json=args).status_code == 409
    app.state.store.publication_result(post["id"], "draft")
    candidate = fixture_spec(); candidate["scenes"][0]["layers"][0]["text"] = "Changed after preview"
    assert save(client, cid, candidate).status_code == 200
    assert client.post(endpoint, json=args).status_code == 409
    assert client.get(f"/api/campaigns/{cid}/final-films").json()["items"] == []
