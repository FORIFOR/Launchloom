"""Cut the raw studio recording into the site (16:9) and X (9:16) videos.

Both are edited from the SAME real recording produced by record-demo.py. No
footage is generated, re-staged or substituted. Where a wait is shortened, the
factor is drawn on screen, because the viewer is entitled to know that the
elapsed time they are watching is not the elapsed time it took.

    python scripts/edit-demo.py --raw docs/video/raw --output homepage
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw
from launchloom.rendering import font

W, H = 1440, 900

# start, end (in the raw recording), speed, caption, zoom target as a fraction
# of the frame (cx, cy, scale) — scale 1.0 is the whole frame.
# Segments are expressed against the marks the recorder wrote, not against
# absolute seconds, so the same plan cuts any take — the Japanese one, the
# English one, or a re-record after the UI moves.
# (start_mark, start_offset, end_mark, end_offset, speed, caption_key, (cx, cy, scale))
PLAN = [
    ('film-play-start', 1.2, 'film-play-start', 4.7, 1.0, 'hook',    (0.45, 0.50, 0.50)),
    ('empty-studio',   -0.9, 'sample-clicked',  0.5, 1.0, 'record',  (0.50, 0.52, 0.92)),
    ('sample-clicked',  0.7, 'review-open',    -0.1, 6.0, 'capture', (0.50, 0.50, 1.00)),
    ('review-open',     0.4, 'caption-saved',   0.5, 1.0, 'edit',    (0.74, 0.47, 0.46)),
    ('render-start',    0.3, 'render-done',    -0.2, 14.0, 'render', (0.50, 0.50, 1.00)),
    ('film-play-start', 3.0, 'film-play-start', 7.4, 1.0, 'result',  (0.45, 0.50, 0.50)),
    ('landing-page',    0.5, 'social-drafts',  -0.2, 1.2, 'outro',   (0.50, 0.50, 0.95)),
]

CAPTIONS = {
    'ja': {'hook': '動画・LP・SNS原稿。ひとつの企画から。', 'record': '① 実画面を自動で収録',
           'capture': '収録中 · 待ち時間を短縮', 'edit': '② 見出しを直して保存',
           'render': 'レンダリング · 待ち時間を短縮', 'result': '③ 直した文字が、動画に入る',
           'outro': '同じ企画から、LPと投稿文も'},
    'en': {'hook': 'One recording. A film, a page and your posts.', 'record': '1 · The real screen, recorded',
           'capture': 'Recording · waiting time sped up', 'edit': '2 · Fix one heading and save',
           'render': 'Rendering · waiting time sped up', 'result': '3 · The edit is in the film',
           'outro': 'Same plan. Landing page and posts too.'},
}
# The portrait cut keeps the three beats that survive a phone screen.
VERTICAL_KEYS = ('hook', 'edit', 'render', 'result')
VERTICAL_CAPTIONS = {
    'ja': {'hook': '動画・LP・SNS原稿を\nひとつの企画から', 'edit': '見出しを直して保存',
           'render': '待ち時間を短縮', 'result': '直した文字が\n動画に入る'},
    'en': {'hook': 'One recording.\nA film, a page, your posts.', 'edit': 'Fix one heading',
           'render': 'Waiting time sped up', 'result': 'The edit is\nin the film'},
}


def resolve(marks, lang, keys=None, captions=None, speed_override=None):
    at = {m['label']: m['t'] for m in marks}
    text = captions or CAPTIONS[lang]
    out = []
    for sm, so, em, eo, speed, key, box in PLAN:
        if keys and key not in keys:
            continue
        if sm not in at or em not in at:
            raise SystemExit(f'the recording has no mark {sm!r}/{em!r}')
        a, b = at[sm] + so, at[em] + eo
        if b <= a:
            raise SystemExit(f'segment {key} is empty: {a:.2f}..{b:.2f}')
        out.append((round(a, 2), round(b, 2), (speed_override or {}).get(key, speed), text[key], box))
    return out


def caption_png(text: str, path: Path, width: int, size: int, pad: int = 28) -> None:
    """Draw the caption with the same font stack the renderer uses."""
    lines = text.split('\n')
    f = font(size, bold=True)
    probe = Image.new('RGBA', (10, 10)); d = ImageDraw.Draw(probe)
    heights = [d.textbbox((0, 0), ln, font=f)[3] for ln in lines]
    line_h = max(heights) + int(size * 0.42)
    h = line_h * len(lines) + pad * 2
    img = Image.new('RGBA', (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, width - 1, h - 1], radius=16, fill=(0, 0, 0, 216))
    y = pad
    for ln in lines:
        w = d.textbbox((0, 0), ln, font=f)[2]
        d.text(((width - w) // 2, y), ln, font=f, fill=(250, 250, 250, 255))
        y += line_h
    img.save(path)


def region(cx: float, cy: float, scale: float, aspect: float = 16 / 9):
    """A static crop rectangle of the given aspect, centred on (cx, cy).

    Computed here rather than in an ffmpeg expression: crop cannot vary its
    width or height over time, and a wrong rectangle is easier to see in
    numbers than in a filter graph.
    """
    cw = min(W * scale, H * scale * aspect)
    ch = cw / aspect
    if ch > H:
        ch = H; cw = ch * aspect
    x = max(0, min(W - cw, W * cx - cw / 2))
    y = max(0, min(H - ch, H * cy - ch / 2))
    return int(cw) // 2 * 2, int(ch) // 2 * 2, int(x) // 2 * 2, int(y) // 2 * 2


def push_in(out_w: int, out_h: int, frames: int, amount: float = 0.12) -> str:
    """A slow centred push-in, so the eye is led without the frame lurching."""
    n = max(frames, 2)
    z = f"min(1+{amount}*on/{n}\\,{1 + amount})"
    return (f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={out_w}x{out_h}:fps=30")


def build(raw: Path, plan, out: Path, mode: str, work: Path) -> float:
    """mode 'site' = 1280x720. mode 'vertical' = 720x1280 with the UI re-laid
    out: the region that matters on top, a large caption below it, never a
    centre crop of the desktop frame."""
    out_w, out_h = (1280, 720) if mode == 'site' else (720, 1280)
    cap_w = int(out_w * (0.86 if mode == 'site' else 0.90))
    cap_size = 34 if mode == 'site' else 44
    parts, filters, labels = [], [], []
    total = 0.0
    for i, (a, b, speed, text, (cx, cy, sc)) in enumerate(plan):
        dur = (b - a) / speed
        total += dur
        frames = int(dur * 30)
        # A 4:3 region for the portrait cut: a 16:9 strip on a 9:16 canvas
        # leaves most of the frame empty.
        cw, ch, cx0, cy0 = region(cx, cy, sc, 16 / 9 if mode == 'site' else 4 / 3)
        cap = work / f'cap-{mode}-{i}.png'
        caption_png(text, cap, cap_w, cap_size)
        parts += ['-ss', f'{a}', '-to', f'{b}', '-i', str(raw), '-i', str(cap)]
        v_in, c_in = f'{i*2}:v', f'{i*2+1}:v'
        if mode == 'site':
            filters.append(
                f'[{v_in}]setpts=PTS/{speed},fps=30,crop={cw}:{ch}:{cx0}:{cy0},'
                f'{push_in(out_w, out_h, frames)},format=yuva420p[s{i}];'
                f'[s{i}][{c_in}]overlay=x=(W-w)/2:y=H-h-{int(out_h*0.055)}[v{i}]')
        else:
            # Re-layout: the cropped region scaled to the full width, seated in
            # the upper half of a portrait canvas, caption underneath it.
            vid_h = int(out_w * ch / cw) // 2 * 2
            top = int(out_h * 0.17)
            filters.append(
                f'[{v_in}]setpts=PTS/{speed},fps=30,crop={cw}:{ch}:{cx0}:{cy0},'
                f'{push_in(out_w, vid_h, frames)},format=yuva420p[s{i}];'
                f'color=c=0x000000:s={out_w}x{out_h}:d={dur:.3f}:r=30,format=yuva420p[bg{i}];'
                f'[bg{i}][s{i}]overlay=x=0:y={top}:shortest=1[m{i}];'
                f'[m{i}][{c_in}]overlay=x=(W-w)/2:y={top + vid_h + int(out_h*0.05)}[v{i}]')
        labels.append(f'[v{i}]')
    graph = ';'.join(filters) + ';' + ''.join(labels) + f'concat=n={len(plan)}:v=1:a=0[out]'
    cmd = ['ffmpeg', '-y', '-v', 'error', *parts, '-filter_complex', graph, '-map', '[out]',
           '-c:v', 'libx264', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
           '-crf', '25', '-preset', 'slow', '-movflags', '+faststart', '-an', str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-3000:]); raise SystemExit(f'ffmpeg failed for {out}')
    return total


def main(raw_dir: Path, output: Path, lang: str, suffix: str):
    raw = raw_dir / 'studio-raw.webm'
    if not raw.exists():
        raise SystemExit(f'no raw recording at {raw}; run scripts/record-demo.py first')
    marks = json.loads((raw_dir / 'marks.json').read_text())['marks']
    output.mkdir(parents=True, exist_ok=True)
    work = output / '.work'; work.mkdir(exist_ok=True)

    site = output / f'studio-demo{suffix}.mp4'
    vert = output / f'studio-demo{suffix}-vertical.mp4'
    t1 = build(raw, resolve(marks, lang), site, 'site', work)
    t2 = build(raw, resolve(marks, lang, VERTICAL_KEYS, VERTICAL_CAPTIONS[lang],
                            {'render': 22.0}), vert, 'vertical', work)

    # Posters come from the raw recording, not the cut: a frame of the cut
    # carries a burned-in caption that repeats the page's own headline and
    # covers the UI the poster is meant to show. Take the review screen, where
    # the studio itself is on screen rather than the sample app it is editing.
    at = {m['label']: m['t'] for m in marks}
    poster_at = at['caption-saved'] - 1.2

    # Landscape: full width of the source, cropped only vertically, so nothing
    # is sliced off the sides.
    lw, lh, lx, ly = region(0.50, 0.50, 1.0)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', f'{poster_at:.2f}', '-i', str(raw),
                    '-frames:v', '1', '-vf', f'crop={lw}:{lh}:{lx}:{ly}', '-q:v', '3',
                    str(output / f'studio-demo{suffix}-poster.jpg')], check=True)

    # Portrait: build the same 720x1280 composition the vertical cut uses. A
    # 4:3 still in a 9:16 frame letterboxes into ~300px of black and eats the
    # phone's first screen.
    vw, vh, vx, vy = region(0.50, 0.50, 0.94, 4 / 3)
    inner_h = int(720 * vh / vw) // 2 * 2
    top = int(1280 * 0.17)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', f'{poster_at:.2f}', '-i', str(raw),
                    '-frames:v', '1', '-filter_complex',
                    f'[0:v]crop={vw}:{vh}:{vx}:{vy},scale=720:{inner_h}[s];'
                    f'color=c=0x000000:s=720x1280[bg];[bg][s]overlay=x=0:y={top}',
                    '-q:v', '3', str(output / f'studio-demo{suffix}-vertical-poster.jpg')], check=True)

    report = {}
    for name, p, planned in ((f'site{suffix}', site, t1), (f'vertical{suffix}', vert, t2)):
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                                'stream=codec_name,width,height,r_frame_rate',
                                '-show_entries', 'format=duration,size', '-of', 'json', str(p)],
                               capture_output=True, text=True).stdout
        d = json.loads(probe)
        rel = p.relative_to(ROOT) if p.is_relative_to(ROOT) else p
        report[name] = {'path': str(rel), 'lang': lang, 'planned_seconds': round(planned, 2),
                        'actual_seconds': round(float(d['format']['duration']), 2),
                        'bytes': int(d['format']['size']), **{k: d['streams'][0][k] for k in
                        ('codec_name', 'width', 'height', 'r_frame_rate')}}
        print(name, report[name])
    report_dir = ROOT / 'docs/video'; report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / 'edit-report.json'
    existing = json.loads(path.read_text()) if path.exists() else {}
    existing.update(report)
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', type=Path, default=ROOT / 'docs/video/raw')
    ap.add_argument('--output', type=Path, default=ROOT / 'homepage')
    ap.add_argument('--lang', default='ja', choices=['ja', 'en'])
    ap.add_argument('--suffix', default='', help="'-en' writes studio-demo-en.mp4")
    a = ap.parse_args()
    main(a.raw, a.output, a.lang, a.suffix)
