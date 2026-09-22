"""Horio Premium Web pre-publish verification for the public homepage.

Checks the real page at 1440px, 1024px and 390px, captures evidence, and
verifies the requested qualitative gates with measurable proxies:
- Logo Swap Test
- Screenshot Test / motion-off state
- service clarity in the first viewport
- real product/output as the dominant visual
- one Signature Moment only
"""
from __future__ import annotations
import argparse, asyncio, json, sys, shutil
from pathlib import Path
from playwright.async_api import async_playwright

SIZES=[(1440,960),(1024,900),(390,844)]

async def main(args):
    report={"url":args.url,"checks":{},"views":{},"errors":[]}
    async with async_playwright() as p:
        browser_path=shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chromium")
        browser=await p.chromium.launch(headless=True, executable_path=browser_path)
        for width,height in SIZES:
            page=await browser.new_page(viewport={"width":width,"height":height},locale="ja-JP")
            page.on("pageerror",lambda e: report["errors"].append(str(e)))
            await page.goto(args.url,wait_until="load")
            await page.wait_for_timeout(1100)
            key=str(width)
            metrics=await page.evaluate("""() => {
              const hero=document.querySelector('.hero');
              const h1=document.querySelector('h1');
              const lede=document.querySelector('.hero .lede');
              const stage=document.querySelector('[data-actual-product]');
              const visible=(el)=>{ if(!el)return false; const r=el.getBoundingClientRect(); const s=getComputedStyle(el); return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'; };
              const vr=(el)=>el?.getBoundingClientRect();
              return {
                overflow:document.documentElement.scrollWidth-innerWidth,
                heroBottom:vr(hero)?.bottom||0,
                h1Bottom:vr(h1)?.bottom||99999,
                ledeBottom:vr(lede)?.bottom||99999,
                stageTop:vr(stage)?.top||99999,
                stageBottom:vr(stage)?.bottom||99999,
                stageArea:(vr(stage)?.width||0)*(vr(stage)?.height||0),
                heroArea:(vr(hero)?.width||0)*(vr(hero)?.height||0),
                actualVisible:visible(stage),
                signatureCount:document.querySelectorAll('[data-signature]').length,
                actualCount:document.querySelectorAll('[data-actual-product]').length,
                visibleLandscape:visible(document.querySelector('.signature .desktop-film')),
                visiblePortrait:visible(document.querySelector('.signature .mobile-film')),
                headline:h1?.innerText||'',
                lede:lede?.innerText||''
              };
            }""")
            report["views"][key]=metrics
            report["checks"][f"no_horizontal_overflow_{width}"]=metrics["overflow"]<=0
            report["checks"][f"hero_message_visible_{width}"]=metrics["h1Bottom"]<=height and metrics["ledeBottom"]<=height*1.18
            report["checks"][f"actual_product_visible_{width}"]=metrics["actualVisible"] and metrics["stageTop"]<=height*1.05
            if width==390:
                report["checks"]["mobile_uses_vertical_real_output"]=metrics["visiblePortrait"] and not metrics["visibleLandscape"]
            else:
                report["checks"][f"desktop_uses_landscape_real_output_{width}"]=metrics["visibleLandscape"] and not metrics["visiblePortrait"]
            await page.screenshot(path=str(args.output/f"homepage-{width}.png"),full_page=True)
            await page.close()

        # Qualitative gates are exercised on the 1440 layout.
        page=await browser.new_page(viewport={"width":1440,"height":960},locale="ja-JP")
        await page.goto(args.url,wait_until="load")
        await page.wait_for_timeout(1200)
        report["checks"]["one_signature_moment"]=(await page.locator('[data-signature]').count())==1
        report["checks"]["real_product_is_primary"] = await page.evaluate("""() => {
          const stage=document.querySelector('[data-actual-product]')?.getBoundingClientRect();
          const others=[...document.querySelectorAll('img')].map(x=>x.getBoundingClientRect()).filter(r=>r.top<innerHeight&&r.width>0&&r.height>0);
          const maxOther=Math.max(0,...others.map(r=>r.width*r.height));
          return !!stage && stage.width*stage.height>maxOther && stage.width>innerWidth*.44;
        }""")
        report["checks"]["first_5_10_seconds_clear"] = await page.evaluate("""() => {
          const text=(document.querySelector('h1')?.innerText||'')+' '+(document.querySelector('.hero .lede')?.innerText||'');
          // The first viewport has to name the input and at least two of the
          // outputs. Concepts, not one particular phrasing.
          const input=/収録|録画|操作画面/.test(text);
          const outputs=['紹介動画','動画','紹介ページ','LP','投稿'].filter(w=>text.includes(w)).length;
          return input && outputs>=2 && !!document.querySelector('[data-actual-product] video');
        }""")

        # Logo Swap Test: after swapping the wordmark, the real product footage and
        # concrete workflow language must still identify what the page is about.
        await page.evaluate("() => {document.querySelector('.brand-name').textContent='ACME';}")
        await page.screenshot(path=str(args.output/'logo-swap-test.png'))
        report["checks"]["logo_swap_test"] = await page.evaluate("""() => {
          const t=document.body.innerText;
          const stage=document.querySelector('[data-actual-product]');
          return !!stage && /収録|録画|操作画面/.test(t) && /完成|投稿準備|紹介動画|投稿文/.test(t) && /Launchloom/.test(stage.innerText + (stage.querySelector('video')?.getAttribute('poster')||''));
        }""")

        # Screenshot Test / motion-off beauty: disable all transitions and verify the
        # composition still communicates through static type + real evidence.
        await page.reload(wait_until='load')
        await page.evaluate("() => document.documentElement.classList.add('motion-off')")
        await page.wait_for_timeout(100)
        await page.screenshot(path=str(args.output/'screenshot-test-motion-off.png'))
        report["checks"]["screenshot_test"] = await page.evaluate("""() => {
          const h=document.querySelector('h1')?.getBoundingClientRect();
          const s=document.querySelector('[data-actual-product]')?.getBoundingClientRect();
          return !!h&&!!s&&h.width>250&&s.width>550&&s.top<innerHeight;
        }""")
        report["checks"]["beautiful_with_motion_stopped"] = await page.evaluate("""() => {
          const stage=document.querySelector('[data-signature]');
          const m=getComputedStyle(stage.querySelector('.stage-media'));
          return m.clipPath==='none' || m.clipPath.includes('inset(0');
        }""")

        # Functional evidence: visible hero film must decode and play only on request.
        film=page.locator('.signature .desktop-film')
        await film.evaluate("v=>{v.muted=true; return v.play()}")
        await page.wait_for_function("() => document.querySelector('.signature .desktop-film').readyState>=2")
        await page.wait_for_timeout(700)
        report["checks"]["actual_film_plays_when_asked"] = await film.evaluate("v=>v.currentTime>0.2&&!v.paused")
        await film.evaluate("v=>v.pause()")
        report["checks"]["internal_hash_links_resolve"] = await page.evaluate("""() => [...document.querySelectorAll('a[href^="#"]')].every(a=>document.getElementById(a.hash.slice(1)))""")
        report["checks"]["real_assets_present"] = await page.evaluate("""() => ['generated-page.png','review-gate.png','film.mp4','film-vertical.mp4'].every(name=>document.documentElement.innerHTML.includes(name))""")
        await page.close(); await browser.close()

    print(json.dumps(report,ensure_ascii=False,indent=2))
    failed=[k for k,v in report["checks"].items() if v is False]
    if failed or report["errors"]:
        sys.exit('Failed: '+', '.join(failed+report["errors"]))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--url',default='http://127.0.0.1:4477/ja/'); ap.add_argument('--output',type=Path,default=Path('checks-hpw'))
    a=ap.parse_args(); a.output.mkdir(parents=True,exist_ok=True); asyncio.run(main(a))
