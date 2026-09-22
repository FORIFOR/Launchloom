"""Record the real studio running the bundled sample, for the site and X videos.

Nothing is simulated: this starts a disposable offline studio, drives it in a
real browser, and records what the browser actually shows. Playwright's video
does not capture the OS cursor, so a visible pointer is drawn into the page and
moved by the same real mouse events that drive the clicks.

    python scripts/record-demo.py --output docs/video/raw

Providers, publishing and paid generation are explicitly disabled, and every
request outside the disposable server's own origin is denied.
"""
from __future__ import annotations
import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
import httpx
from playwright.sync_api import sync_playwright
from first_success_browser_journey import offline_settings, TOKEN

WIDTH, HEIGHT = 1440, 900
# Scene 2 on purpose: the film's first three seconds draw brief.tagline
# (rendering.py), so editing scene 1's title would not appear on screen and
# the video would be claiming something the frames do not show.
EDITED_BY_LANG = {'ja': '思いついた瞬間に、書き留める。',
                  'en': 'Write it down the moment it lands.'}

# A pointer drawn into the page: Playwright's recording has no OS cursor, and a
# viewer has to be able to follow what is being clicked.
POINTER = """
(() => {
  const dot = document.createElement('div');
  dot.id = '__rec_pointer';
  dot.style.cssText = 'position:fixed;left:0;top:0;width:18px;height:18px;margin:-9px 0 0 -9px;'
    + 'border-radius:50%;background:rgba(254,110,0,.95);box-shadow:0 0 0 3px rgba(255,255,255,.75),0 2px 10px rgba(0,0,0,.6);'
    + 'z-index:2147483647;pointer-events:none;transition:transform .08s ease-out';
  const ring = document.createElement('div');
  ring.style.cssText = 'position:fixed;left:0;top:0;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;'
    + 'border:2px solid rgba(254,110,0,.9);z-index:2147483646;pointer-events:none;opacity:0';
  const add = () => { if (document.body) { document.body.append(dot, ring); } };
  if (document.body) add(); else document.addEventListener('DOMContentLoaded', add);
  addEventListener('mousemove', (e) => {
    dot.style.left = ring.style.left = e.clientX + 'px';
    dot.style.top = ring.style.top = e.clientY + 'px';
  }, true);
  addEventListener('mousedown', () => {
    dot.style.transform = 'scale(.7)';
    ring.style.transition = 'none'; ring.style.opacity = '1'; ring.style.transform = 'scale(1)';
    requestAnimationFrame(() => {
      ring.style.transition = 'transform .5s ease-out, opacity .5s ease-out';
      ring.style.transform = 'scale(3.2)'; ring.style.opacity = '0';
    });
  }, true);
  addEventListener('mouseup', () => { dot.style.transform = 'scale(1)'; }, true);
})();
"""


def serve(data, port):
    import uvicorn
    from launchloom.server import create_app
    uvicorn.run(create_app(offline_settings(data, port)), host='127.0.0.1', port=port,
                log_level='error', access_log=False)


def main(output: Path, lang: str = 'ja'):
    output.mkdir(parents=True, exist_ok=True)
    marks = []          # (seconds_from_start, label) — the edit script uses these
    with tempfile.TemporaryDirectory(prefix='launchloom-record-') as tmp:
        data = Path(tmp)
        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]; sock.close()
        base = f'http://127.0.0.1:{port}'
        env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'LANG') if k in os.environ}
        env['PYTHONPATH'] = str(ROOT)
        proc = subprocess.Popen([sys.executable, __file__, '--serve', str(data), str(port)], env=env)
        try:
            for _ in range(300):
                try:
                    httpx.get(base + '/healthz', timeout=1); break
                except Exception:
                    time.sleep(.2)
            with sync_playwright() as p:
                browser = p.chromium.launch(channel='chrome', headless=True)
                context = browser.new_context(
                    viewport={'width': WIDTH, 'height': HEIGHT}, device_scale_factor=1,
                    locale='ja-JP' if lang == 'ja' else 'en-US',
                    record_video_dir=str(output), reduced_motion='no-preference',
                    record_video_size={'width': WIDTH, 'height': HEIGHT})
                context.route('**/*', lambda r: r.continue_() if r.request.url.startswith(base + '/') else r.abort())
                context.add_init_script(POINTER)
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                start = time.monotonic()

                def mark(label):
                    marks.append({'t': round(time.monotonic() - start, 2), 'label': label})
                    print(f'{marks[-1]["t"]:7.2f}  {label}', flush=True)

                def glide(selector, steps=26):
                    """Move the real mouse to an element so the drawn pointer follows."""
                    box = page.locator(selector).first.bounding_box()
                    page.locator(selector).first.scroll_into_view_if_needed()
                    box = page.locator(selector).first.bounding_box()
                    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2, steps=steps)
                    page.wait_for_timeout(180)

                page.goto(base)
                page.locator('#access-dialog[open]').wait_for()
                page.keyboard.insert_text(TOKEN); page.keyboard.press('Tab'); page.keyboard.press('Enter')
                page.locator('#first-success-title').wait_for()
                # The studio may already be in the wanted language (it follows the
                # browser locale), so read it before touching the toggle.
                if page.evaluate('() => document.documentElement.lang') != lang:
                    page.locator('#language-toggle').click()
                    page.wait_for_function("(l) => document.documentElement.lang===l", arg=lang, timeout=20000)
                    page.wait_for_timeout(600)
                page.mouse.move(WIDTH * 0.5, HEIGHT * 0.5)
                page.wait_for_timeout(1400)
                mark('empty-studio')

                glide('[data-sample]')
                page.wait_for_timeout(500)
                page.locator('[data-sample]').first.click()
                mark('sample-clicked')

                page.locator('#review-panel-title').wait_for(timeout=300000)
                page.wait_for_timeout(1500)
                mark('review-open')

                # Edit a real caption field and save it. Centre it first: the
                # recording has to show the field, not its top edge.
                field = page.locator('.scene-edit').nth(1).locator('input').first
                field.evaluate("(el)=>el.scrollIntoView({block:'center'})")
                page.wait_for_timeout(700)
                box = field.bounding_box()
                page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2, steps=26)
                page.wait_for_timeout(180)
                field.click()
                page.keyboard.press('Meta+A' if sys.platform == 'darwin' else 'Control+A')
                page.wait_for_timeout(250)
                EDITED = EDITED_BY_LANG[lang]
                for ch in EDITED:
                    page.keyboard.type(ch)
                    page.wait_for_timeout(55)
                page.wait_for_timeout(700)
                mark('caption-typed')

                dirty_text = page.locator('#plan-save-state').inner_text().strip()
                glide('#save-plan')
                page.locator('#save-plan').click()
                # Wait for the studio to say it is showing saved content, rather
                # than assuming the PATCH landed.
                # Language-independent: wait for the状態 line to stop saying
                # "unsaved", whatever language it is saying it in.
                page.wait_for_function(
                    "(before) => { const el = document.getElementById('plan-save-state');"
                    " return el && el.textContent.trim() && el.textContent.trim() !== before; }",
                    arg=dirty_text, timeout=30000)
                page.wait_for_timeout(900)
                mark('caption-saved')

                glide('#approve-plan')
                page.locator('#approve-plan').click()
                mark('render-start')

                page.locator('#film-player').wait_for(timeout=300000)
                page.wait_for_function("() => document.getElementById('film-player')?.readyState>=2", timeout=180000)
                mark('render-done')

                # The edit has to be in the exported captions, or the video would
                # be claiming a result the product did not produce. Fail loudly
                # rather than record a false claim.
                cid = page.evaluate("() => new URL(location.href).searchParams.get('campaign')")
                srt = httpx.get(f'{base}/artifacts/{cid}/captions.srt',
                                headers={'Authorization': 'Bearer ' + TOKEN}, timeout=30)
                ok = srt.status_code == 200 and EDITED in srt.text
                print(f'  captions.srt {srt.status_code}; contains the edit: {ok}', flush=True)
                if not ok:
                    raise SystemExit('the edit is not in the exported captions — refusing to record a false claim')

                # Bring the player into frame before playing it: this is the shot
                # the whole video opens on.
                page.locator('#film-player').evaluate("(v)=>v.scrollIntoView({block:'center'})")
                page.wait_for_timeout(900)
                page.mouse.move(WIDTH * 0.42, HEIGHT * 0.55, steps=20)
                page.locator('#film-player').evaluate('(v)=>{v.muted=true;v.currentTime=0;v.play()}')
                mark('film-play-start')
                page.wait_for_timeout(11000)
                mark('film-playing')

                page.evaluate('() => scrollTo({top:0})')
                page.wait_for_timeout(500)
                glide('[data-tab="site"]')
                page.locator('[data-tab="site"]').click()
                page.wait_for_timeout(3200)
                mark('landing-page')

                glide('[data-tab="distribution"]')
                page.locator('[data-tab="distribution"]').click()
                page.wait_for_timeout(3000)
                mark('social-drafts')

                page.wait_for_timeout(600)
                video = page.video.path()
                context.close()
                browser.close()
        finally:
            proc.terminate(); proc.wait(timeout=20)

    raw = output / 'studio-raw.webm'
    if raw.exists():
        raw.unlink()
    Path(video).rename(raw)
    (output / 'marks.json').write_text(json.dumps({'marks': marks, 'width': WIDTH, 'height': HEIGHT,
                                                   'edited_caption': EDITED}, ensure_ascii=False, indent=2))
    print('\nraw:', raw, raw.stat().st_size, 'bytes')
    print('page errors:', errors)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--serve':
        serve(Path(sys.argv[2]), int(sys.argv[3]))
    else:
        ap = argparse.ArgumentParser()
        ap.add_argument('--output', type=Path, default=ROOT / 'docs/video/raw')
        ap.add_argument('--lang', default='ja', choices=['ja', 'en'])
        a = ap.parse_args()
        main(a.output, a.lang)
