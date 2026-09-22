"""Check the public homepage in a real browser at phone, tablet and desktop.

Serves homepage/ over HTTP (file:// would not match how it is published) and
asserts what a visitor actually gets: no horizontal overflow, the hero video
present with a poster, and playback that really advances.

    python scripts/verify-homepage.py --output docs/video/site-check
"""
from __future__ import annotations
import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import httpx
from playwright.sync_api import sync_playwright

WIDTHS = [(390, 844, 'phone'), (768, 1024, 'tablet'), (1440, 900, 'desktop')]


def main(output: Path, pages):
    output.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]; sock.close()
    server = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1'],
                              cwd=ROOT / 'homepage', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    report = []
    try:
        for _ in range(100):
            try:
                httpx.get(base + '/', timeout=1); break
            except Exception:
                time.sleep(.1)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            for path, name in pages:
                for w, h, label in WIDTHS:
                    ctx = browser.new_context(viewport={'width': w, 'height': h}, device_scale_factor=2,
                                              locale='ja-JP' if name == 'ja' else 'en-US')
                    page = ctx.new_page()
                    errors, missing = [], []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.on('response', lambda r: missing.append(f'{r.status} {r.url}') if r.status >= 400 else None)
                    page.goto(base + path, wait_until='load')
                    page.wait_for_timeout(1200)
                    dims = page.evaluate('({v:innerWidth,d:document.documentElement.scrollWidth})')
                    video = page.locator('.stage-media video:visible').first
                    info = video.evaluate("""(v) => ({src: v.currentSrc.split('/').pop(), poster: v.poster.split('/').pop(),
                        muted: v.muted, autoplay: v.autoplay, controls: v.controls, w: v.videoWidth, h: v.videoHeight})""")
                    video.evaluate('(v)=>{v.muted=true;return v.play()}')
                    page.wait_for_timeout(2500)
                    played = video.evaluate('(v)=>({t:v.currentTime, ready:v.readyState})')
                    page.screenshot(path=str(output / f'{name}-{label}.png'), full_page=False)
                    report.append({'page': name, 'width': w, 'overflow': dims['d'] > dims['v'] + 1,
                                   'scrollWidth': dims['d'], 'video': info,
                                   'playback_seconds': round(played['t'], 2), 'readyState': played['ready'],
                                   'page_errors': errors, 'http_errors': missing})
                    print(f"{name:3} {label:8} overflow={report[-1]['overflow']} "
                          f"src={info['src']} {info['w']}x{info['h']} played={played['t']:.2f}s "
                          f"errors={len(errors)}/{len(missing)}")
                    ctx.close()
            browser.close()
    finally:
        server.terminate(); server.wait(timeout=10)
    (output / 'homepage-check.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
    bad = [r for r in report if r['overflow'] or r['playback_seconds'] <= 0 or r['page_errors'] or r['http_errors']]
    print('\nFAILURES:', len(bad))
    for r in bad:
        print(' ', r['page'], r['width'], 'overflow' if r['overflow'] else '',
              'no playback' if r['playback_seconds'] <= 0 else '', r['page_errors'], r['http_errors'][:3])
    return 1 if bad else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, default=ROOT / 'docs/video/site-check')
    sys.exit(main(ap.parse_args().output, [('/', 'en'), ('/ja/', 'ja')]))
