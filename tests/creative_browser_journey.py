"""Real localhost UI -> authenticated API -> FFmpeg -> immutable finished film.

Uses only a labelled typography fixture. No provider, agent, Adobe or social
account is called. Screenshots contain no access key or private product material.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from playwright.sync_api import sync_playwright, expect
import uvicorn

from launchloom.config import Settings
from launchloom.server import create_app
from launchloom.creative import BrandProfile, CreativeLayer, CreativeScene, CreativeSpec


def main():
    output = Path(os.getenv("CREATIVE_BROWSER_ARTIFACTS", "creative-browser-artifacts"))
    output.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        token = "creative-browser-fixture-local-token"
        app = create_app(Settings(data_dir=root, token=token, enable_paid_generation=False,
                                  enable_live_publish=False), run_worker=False)
        campaign = app.state.store.create_campaign({
            "name": "Type study", "tagline": "Make it seen.", "audience": "Designers", "language": "ja",
            "features": [{"title": "Typography study", "detail": "Local type exercise, not a product demo.",
                          "approved": True, "evidence": "Operator-authored testing fixture."}], "channels": ["x"]})
        cid = campaign["id"]
        spec = CreativeSpec(title="Typography study", brand=BrandProfile(name="Launchloom"), scenes=[
            CreativeScene(id="opening", purpose="hook", seconds=.8,
                          layers=[CreativeLayer(id="headline", kind="text", role="copy", text="つくったものに、光を。")]),
            CreativeScene(id="closing", purpose="cta", seconds=.8,
                          layers=[CreativeLayer(id="headline", kind="text", role="copy", text="Make it seen.")])])
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        address = f"http://127.0.0.1:{port}"
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
        thread = threading.Thread(target=server.run, daemon=True); thread.start()
        try:
            with httpx.Client(base_url=address, headers={"Authorization": "Bearer " + token}) as client:
                for _ in range(150):
                    try:
                        if client.get("/healthz").is_success: break
                    except httpx.ConnectError: pass
                    time.sleep(.1)
                else: raise AssertionError("Local server did not start")
                state = client.get(f"/api/campaigns/{cid}/creative-spec").json()
                response = client.put(f"/api/campaigns/{cid}/creative-spec", json={
                    "spec": spec.model_dump(), "expected_revision": state["revision"],
                    "production_revision": state["production_revision"]})
                response.raise_for_status()
                with sync_playwright() as playwright:
                    # Official Chrome includes the H.264/AAC codecs that the product exports.
                    # The workflow uses the stock runner browser; no policies are bypassed.
                    executable = os.getenv("CHROMIUM_EXECUTABLE")
                    browser = playwright.chromium.launch(headless=True, executable_path=executable,
                        channel=None if executable else os.getenv("CREATIVE_BROWSER_CHANNEL", "chrome"),
                        args=["--no-sandbox"])
                    page = browser.new_page(viewport={"width": 1440, "height": 1100}, locale="ja-JP")
                    errors = []; page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(f"{address}/creative?campaign={cid}")
                    expect(page.locator("#access-form")).to_be_visible()
                    page.locator("#access-key").fill(token)
                    page.locator("#access-form button").click()
                    expect(page.locator("#workspace")).to_be_visible()
                    page.locator("#rights").check()
                    page.locator("#render-all").click()
                    expect(page.locator("#message")).to_contain_text("レンダーが完了", timeout=60000)
                    expect(page.locator("#film")).to_be_visible()
                    # A visible <video> is not proof of playback. Require decoded frames
                    # and advancing time before taking the screenshot or adopting.
                    try:
                        page.locator("#film").evaluate("""el => {
                            el.muted = true;
                            return Promise.race([el.play(), new Promise((_, reject) =>
                                setTimeout(() => reject(new Error('Video did not start')), 15000))]);
                        }""")
                        page.wait_for_function("""() => {
                            const v = document.querySelector('#film');
                            return v.readyState >= 2 && !v.error && v.videoWidth === 1280 && v.currentTime > 0.25;
                        }""", timeout=20000)
                        page.locator("#film").evaluate("el => { el.pause(); }")
                    except Exception:
                        (output / "video-diagnostic.json").write_text(json.dumps(page.locator("#film").evaluate("""v => ({
                            readyState:v.readyState, networkState:v.networkState, videoWidth:v.videoWidth,
                            error:v.error ? {code:v.error.code, message:v.error.message} : null
                        })"""), indent=2))
                        page.screenshot(path=str(output / "creative-failed-playback.png"), full_page=True)
                        raise
                    page.screenshot(path=str(output / "creative-desktop.png"), full_page=True)
                    page.locator("#portrait").click()
                    page.locator("#instruction").fill("文字を上へ")
                    page.locator("#quick-edit button").click()
                    expect(page.locator("#message")).to_contain_text("下書きに反映")
                    assert float(page.locator("#caption-y").input_value()) == .7
                    page.locator("#save").click()
                    expect(page.locator("#save-state")).to_have_text("保存済み")
                    page.locator("#render-all").click()
                    expect(page.locator("#message")).to_contain_text("レンダーが完了", timeout=60000)
                    jobs = client.get(f"/api/campaigns/{cid}/creative-renders").json()["items"]
                    rebuilt = [(x["scene_id"], x["output"]) for x in jobs[0]["result"]["scenes"] if not x["reused"]]
                    assert rebuilt == [("opening", "portrait")], rebuilt
                    page.locator("#reviewed").check()
                    page.locator("#adopt").click()
                    expect(page.locator("#message")).to_contain_text("新しい完成動画として採用", timeout=30000)
                    assert len(client.get(f"/api/campaigns/{cid}/final-films").json()["items"]) == 1
                    assert app.state.store.campaign(cid)["released"] == 0
                    assert app.state.store.publications(cid) == []
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.locator("#layout-mode").click()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(path=str(output / "creative-mobile.png"), full_page=True)
                    assert not errors, errors
                    browser.close()
                    (output / "result.json").write_text(json.dumps({
                        "passed": True, "real_ffmpeg": True, "real_api": True,
                        "portrait_only_rebuild": rebuilt, "adoption_count": 1,
                        "publications": 0, "decoded_browser_playback": True, "page_errors": errors}, ensure_ascii=False, indent=2))
                    print("PASS: real UI/API/FFmpeg and decoded browser playback; portrait-only rebuild; adoption; mobile overflow; no publication")
        finally:
            server.should_exit = True; thread.join(timeout=15)


if __name__ == "__main__":
    main()
