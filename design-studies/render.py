"""Render proposed UI studies; never record an AI or production application."""
from pathlib import Path
import argparse
import hashlib
import html
import json
import shutil
import subprocess
from playwright.sync_api import sync_playwright

IDS = ['genie', 'ai-meeting', 'oathra', 'aisecure', 'agent-team', 'launchloom']
NAMES = ['Genie', 'AI Meeting', 'Oathra', 'AI Secure', 'Agent Team', 'Launchloom']
ROOT = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=ROOT / 'rendered')
    parser.add_argument('--fps', type=int, default=24)
    args = parser.parse_args()
    if not 12 <= args.fps <= 30: raise ValueError('Frame rate must be 12–30')
    args.out.mkdir(parents=True, exist_ok=True)
    source = (ROOT / 'index.html').read_text(encoding='utf-8')
    items = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium') or None)
        page = browser.new_page(viewport={'width': 1920, 'height': 1080}, device_scale_factor=1)
        failures = []
        page.on('pageerror', lambda error: failures.append(str(error)))
        page.set_content(source, wait_until='load')
        page.evaluate("document.body.classList.add('render');dispatchEvent(new Event('resize'))")
        for product in IDS:
            page.evaluate('(id)=>motion.setup(id)', product)
            for t in [0, 4, 8, 13, 17.5]:
                page.evaluate('(t)=>motion.seek(t)', t)
                assert page.locator('#body').evaluate('(e)=>e.scrollHeight<=e.clientHeight+1'), (product, t)
                assert page.locator('.sample').is_visible()
                assert 'NOT A LIVE PRODUCT DEMO' in page.locator('.notice').inner_text()
            page.evaluate('motion.seek(13)')
            page.screenshot(path=str(args.out / (product + '-poster.png')))
            target = args.out / (product + '-design-preview.mp4')
            temporary = target.with_suffix('.tmp.mp4')
            encoder = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-framerate', str(args.fps), '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(temporary)], stdin=subprocess.PIPE)
            try:
                for frame in range(args.fps * 18):
                    page.evaluate('(t)=>motion.seek(t)', frame / args.fps)
                    encoder.stdin.write(page.screenshot(type='jpeg', quality=94))
                encoder.stdin.close()
                if encoder.wait(timeout=60): raise RuntimeError('Encoding failed')
            except Exception:
                encoder.kill()
                raise
            temporary.replace(target)
            metadata = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_name,width,height,r_frame_rate', '-of', 'json', str(target)], text=True))
            assert float(metadata['format']['duration']) == 18
            assert metadata['streams'][0]['width'] == 1920
            items.append({'id': product, 'mode': 'design-prototype', 'live_product_recording': False, 'file': target.name, 'bytes': target.stat().st_size, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'media': metadata})
            print(product, target.stat().st_size, flush=True)
        assert not failures, failures
        browser.close()
    (args.out / 'index.html').write_text(source, encoding='utf-8')
    (args.out / 'manifest.json').write_text(json.dumps({'scope': 'Proposed UI, sample data, no AI or external service execution', 'items': items}, indent=2), encoding='utf-8')
    cards = ''.join(f'<article id="{product}"><h2>{html.escape(name)}</h2><video controls playsinline preload="none" poster="{product}-poster.png" src="{product}-design-preview.mp4" aria-label="{html.escape(name)}のUI設計プレビュー"></video><p>18秒・1920×1080・24fps・音声なし。提案画面とサンプルデータ。</p><a href="index.html?product={product}">操作できる設計プレビュー</a> <a href="{product}-design-preview.mp4" download>MP4を保存</a></article>' for product, name in zip(IDS, NAMES))
    gallery = '''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Reachmade — UI design films</title><meta name="description" content="6製品の提案UIを18秒の動画で紹介。現行製品の実演ではありません。"><style>body{font-family:system-ui,sans-serif;background:#f6f5f1;color:#202824;margin:0;line-height:1.8}main{max-width:1280px;margin:auto;padding:44px 24px}header{max-width:780px;margin-bottom:40px}h1{font-size:clamp(30px,4vw,48px);line-height:1.35}h2{font-size:24px}p{color:#5c6962}.notice{border-left:3px solid #9b613c;padding:12px 18px;background:#f1eade}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:36px 24px}article{border-top:1px solid #d4dbd3;padding-top:12px;min-width:0}video{width:100%;aspect-ratio:16/9;border:1px solid #d4dbd3;border-radius:10px;display:block;background:#fff}article p{font-size:14px}a{display:inline-block;padding:8px 12px 8px 0;color:inherit;min-height:28px}a:focus-visible{outline:3px solid #37674c;outline-offset:3px}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style></head><body><main><header><a href="https://reachmade.com/">Reachmade</a><h1>画面の理想を、先に動かす。</h1><p>6製品のUIを検討するために制作した、動画と操作プレビューです。各画面は同じHTML/CSSから再現できます。</p><p class="notice"><strong>UI設計プレビューです。現在の製品の実演ではありません。</strong><br>AI、実電話、予約台帳、セキュリティ操作、SNS投稿には接続していません。今後の製品実装の参照用として公開しています。</p></header><div class="grid">''' + cards + '</div><footer><p>Design studies / Reachmade Lab · <a href="manifest.json">制作情報</a></p></footer></main></body></html>'
    (args.out / 'gallery.html').write_text(gallery, encoding='utf-8')

if __name__ == '__main__': main()
