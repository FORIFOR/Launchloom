"""Immutable, revision-bound launch kit. No deployment or publishing side effects."""
from __future__ import annotations
import html
import json
import os
import shutil
import zipfile
from pathlib import Path

from .creative import CreativeSpec, creative_revision
from .creative_rendering import command, child, file_hash
from .models import Brief
from .planning import with_utm, x_weight
from .post_copy import fit_post


def headline(scene):
    return '\n'.join(layer.text for layer in scene.layers if layer.kind=='text')


def campaign_copy(spec: CreativeSpec, brief: Brief, cid: str) -> dict:
    scenes = [{'scene_id':s.id,'purpose':s.purpose,'claim_ids':s.claim_ids,'text':headline(s)} for s in spec.scenes]
    lead = next((s['text'] for s in scenes if s['purpose']=='hook' and s['text']), spec.title)
    cta = next((s['text'] for s in reversed(scenes) if s['purpose']=='cta' and s['text']), '')
    revision = creative_revision(spec)
    posts = []
    for channel in brief.channels:
        url = with_utm(brief.product_url, channel, cid, revision[:12])
        middle = [s['text'] for s in scenes if s['purpose'] not in {'hook','cta'} and s['text']]
        parts = [lead] + middle[:1] + ([cta] if cta and cta != lead else [])
        base = '\n\n'.join(parts)
        text = base + ('\n\n'+url if url else '')
        if channel in {'x','bluesky'}:
            text = fit_post(base,url,280 if channel=='x' else 300,x_weight if channel=='x' else len)
        media = 'portrait.mp4' if channel in {'youtube','instagram','tiktok'} and 'portrait' in spec.outputs else 'landscape.mp4' if 'landscape' in spec.outputs else 'portrait.mp4'
        posts.append({'channel':channel,'content':text,'media':media,'state':'draft','revision':revision,
                      'utm_url':url,'content_review_required':True,
                      'warning': 'Sample campaign; not a claim about another product.' if brief.is_sample else ('No public product URL is configured.' if not url else None)})
    return {'revision':revision, 'title':spec.title, 'brand_name':spec.brand.name,
            'hero':lead, 'cta':cta, 'scenes':scenes, 'posts':posts}


def srt_time(seconds):
    ms=round(seconds*1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'


def write_package(spec: CreativeSpec, brief: Brief, cid: str, sources: dict, destination: Path) -> dict:
    """Build in a new private directory; caller installs atomically after review.

    No creative-spec JSON or private evidence is exported. Copy that the operator
    put on-screen can itself be private; the review gate must say what leaves.
    """
    if set(sources) != set(spec.outputs):
        raise ValueError('Render every enabled aspect from this same revision before exporting a kit')
    destination.mkdir(parents=True,exist_ok=False)
    copy=campaign_copy(spec,brief,cid); esc=html.escape
    for output,(source,sha) in sources.items():
        if source.is_symlink() or file_hash(source)!=sha:
            raise ValueError('Rendered media changed before kit export')
        target=child(destination,output+'.mp4');shutil.copyfile(source,target)
        if file_hash(target)!=sha:
            raise ValueError('Rendered media changed during kit export')
    primary='landscape' if 'landscape' in sources else 'portrait'
    command(['ffmpeg','-v','error','-nostdin','-protocol_whitelist','file,pipe','-ss','0.25','-i',
             str(destination/(primary+'.mp4')),'-frames:v','1','-threads','1',str(destination/'poster.jpg')],timeout=30)
    cursor=0;captions=[]
    for scene in spec.scenes:
        end=cursor+round(scene.seconds*spec.fps)/spec.fps
        text=headline(scene)
        if text:
            captions.append(f'{len(captions)+1}\n{srt_time(cursor)} --> {srt_time(end)}\n{text}')
        cursor=end
    (destination/'captions.srt').write_text('\n\n'.join(captions)+'\n',encoding='utf-8')
    (destination/'posts.json').write_text(json.dumps(copy['posts'],ensure_ascii=False,indent=2),encoding='utf-8')
    (destination/'copy.json').write_text(json.dumps({k:v for k,v in copy.items() if k!='posts'},ensure_ascii=False,indent=2),encoding='utf-8')
    (destination/'social-copy.md').write_text('\n\n'.join(f"## {p['channel']} · draft\n\n{p['content']}" for p in copy['posts']),encoding='utf-8')
    site=destination/'site';site.mkdir()
    sections=''.join(f'<section><h2>{esc(s["text"])}</h2></section>' for s in copy['scenes'] if s['purpose'] not in {'hook','cta'} and s['text'])
    if brief.product_url:
        action=f'<a class="cta" href="{esc(brief.product_url,quote=True)}" rel="noopener noreferrer">{esc(copy["cta"] or ("製品を試す" if brief.language=="ja" else "Try the product"))}</a>'
    else:
        action=f'<p class="notice">{"公開URLが未設定です。" if brief.language=="ja" else "No public product URL is configured."}</p>'
    sample='<p class="notice">SAMPLE · 検証用キャンペーン</p>' if brief.is_sample else ''
    page=f'''<!doctype html><html lang="{brief.language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="launchloom-revision" content="{copy['revision']}"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self'; media-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'"><title>{esc(spec.title)}</title><link rel="stylesheet" href="site.css"></head><body><main><header>{esc(spec.brand.name)}</header>{sample}<h1>{esc(copy['hero'])}</h1><video controls playsinline preload="metadata" poster="../poster.jpg"><source src="../{primary}.mp4" type="video/mp4"></video>{sections}<footer>{action}</footer></main></body></html>'''
    (site/'index.html').write_text(page,encoding='utf-8')
    themes={'editorial':('#F6F5F0','#20251F'),'spotlight':('#171A17','#F6F5F0'),'grid':('#EDF1EC','#20251F')}
    bg,ink=themes[spec.brand.preset]
    css=f'''*{{box-sizing:border-box}}body{{margin:0;background:{bg};color:{ink};font:18px/1.7 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:32px 24px}}header{{font-weight:700;border-bottom:1px solid {ink};padding-bottom:24px}}h1{{font-size:clamp(32px,6vw,76px);line-height:1.2;letter-spacing:-.04em;max-width:900px;white-space:pre-wrap;overflow-wrap:anywhere}}video{{width:100%;max-height:75vh;background:#171A17;border-radius:12px}}section{{padding:44px 0;border-bottom:1px solid {ink};white-space:pre-wrap;overflow-wrap:anywhere}}h2{{font-size:clamp(22px,3vw,38px);line-height:1.4}}footer{{padding:48px 0}}.cta{{display:inline-block;background:{ink};color:{bg};padding:16px 24px;border-radius:8px;text-decoration:none;white-space:pre-wrap;overflow-wrap:anywhere}}.notice{{border-left:4px solid {spec.brand.accent};padding-left:16px}}'''
    (site/'site.css').write_text(css,encoding='utf-8')
    (destination/'README.txt').write_text('Local launch kit. Open site/index.html through a local static server.\nPosts are drafts, not publication receipts. No tracking or analytics is installed.\nVideo, page, captions and posts derive from revision '+copy['revision']+'\n',encoding='utf-8')
    files={p.relative_to(destination).as_posix():file_hash(p) for p in destination.rglob('*') if p.is_file()}
    manifest={'schema_version':1,'creative_revision':copy['revision'],'outputs':{o:sha for o,(_,sha) in sources.items()},
              'files':files,'published':False,'deployed':False,'content_review_required':True,
              'ai_generated':any(l.kind=='generated_video' for s in spec.scenes for l in s.layers)}
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest


def zip_package(folder: Path, destination: Path) -> None:
    # Explicit members only; never package unrelated data from the campaign root.
    names=['manifest.json','README.txt','copy.json','captions.srt','posts.json','social-copy.md','poster.jpg','site/index.html','site/site.css']
    manifest=json.loads((folder/'manifest.json').read_text())
    names += [o+'.mp4' for o in manifest['outputs']]
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name in names:
            path=child(folder,*name.split('/'))
            if not path.is_file():
                raise ValueError('Kit member is missing')
            z.write(path,name,compress_type=zipfile.ZIP_STORED if name.endswith('.mp4') else zipfile.ZIP_DEFLATED)
