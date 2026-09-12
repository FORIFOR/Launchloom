from __future__ import annotations
import html
import json
import shutil
from pathlib import Path
from .models import Brief
from .config import Settings
from .security import tracking_token

TEMPLATE_DIR=Path(__file__).parent/'templates'

def build_site(brief: Brief,cid: str,dest: Path,settings: Settings,has_film: bool=False):
    dest.mkdir(parents=True,exist_ok=True)
    esc=html.escape;ja=brief.language=='ja'
    features=''.join(f'''<article class="feature reveal"><span class="number">0{i+1}</span><div><h3>{esc(f.title)}</h3><p>{esc(f.detail)}</p></div></article>''' for i,f in enumerate(f for f in brief.features if f.approved))
    cta_text='実際に使ってみる' if ja else 'Try it for yourself'
    cta=f'<a class="button primary cta" href="{esc(brief.product_url,quote=True)}" rel="noopener noreferrer">{cta_text}<span>↗</span></a>' if brief.product_url else f'<button class="button primary" disabled>{"公開URLを設定してください" if ja else "Add your product URL"}</button>'
    film='<video id="product-film" controls playsinline preload="metadata" poster="poster.jpg"><source src="film.mp4" type="video/mp4"></video>' if has_film else '<div class="film-pending">'+('操作動画は制作後にここへ入ります。' if ja else 'Your product film belongs here.')+'</div>'
    tracking={'endpoint':settings.tracking_base.rstrip('/')+'/collect' if settings.tracking_base else '', 'campaign_id':cid,'token':tracking_token(settings.token,cid)}
    body=(TEMPLATE_DIR/'site.html').read_text()
    replacements={'LANG':brief.language,'NAME':esc(brief.name),'TAGLINE':esc(brief.tagline),'AUDIENCE':esc(brief.audience),'DESCRIPTION':esc(brief.description or brief.tagline),'ACCENT':brief.accent,'CTA':cta,'FEATURES':features,'FILM':film,
      'KICKER':'大切なことに、余白を。' if ja else 'A little more room for what matters.',
      'WATCH':'実際の動きを見る' if ja else 'Watch it in action',
      'FEATURE_TITLE':'説明よりも、<br>使うとわかる。' if ja else 'Less explaining.<br>More experiencing.',
      'FOOTER_TITLE':'次の一歩を、<br>ここから。' if ja else 'Your next chapter<br>starts here.',
      'SAMPLE':'<span class="sample-note">SAMPLE PRODUCT · 実装済みサンプルアプリのデモ</span>' if brief.is_sample else '',
      'TRACKING':esc(json.dumps(tracking),quote=True)}
    for k,v in replacements.items():body=body.replace('{{'+k+'}}',v)
    (dest/'index.html').write_text(body)
    for name in ('site.css','site.js'):shutil.copy(TEMPLATE_DIR/name,dest/name)
