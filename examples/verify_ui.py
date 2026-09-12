"""Visual/component checks against owned output, or a normal running studio.

Normal machine: python examples/verify_ui.py --data .launchloom --output ./checks
Restricted test browser: add --snapshot. Snapshot mode uses actual API data and
owned media in memory; it does NOT test browser network, cookie/CSP or URL capture.
It does not change browser administrative policies or navigate to blocked URLs.
"""
from __future__ import annotations
import argparse
import asyncio
import base64
import json
import os
import shutil
from pathlib import Path
import httpx
from playwright.async_api import async_playwright

async def main(args):
    token=os.getenv('LAUNCHLOOM_TOKEN')
    if not token:token=(args.data/'access-token').read_text().strip()
    with httpx.Client(base_url=args.base,headers={'Authorization':'Bearer '+token}) as client:
        campaigns=client.get('/api/campaigns').json()
        campaign=client.get('/api/campaigns/'+campaigns[0]['id']).json()
        config=client.get('/api/config').json()
    if campaign['state']!='ready':raise RuntimeError('The latest campaign is not ready')
    cid=campaign['id'];root=args.data/'campaigns'/cid
    source=Path(__file__).resolve().parents[1]/'launchloom'
    args.output.mkdir(parents=True,exist_ok=True)
    # Every page expression below is a function, not a string: the studio serves
    # Content-Security-Policy script-src 'self', so string evaluation is blocked.
    report={'mode':'offline component snapshots' if args.snapshot else 'live browser','campaign_id':cid,'checks':{},'page_errors':[]}
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=os.getenv('CHROMIUM_EXECUTABLE') or shutil.which('chromium') or shutil.which('chromium-browser'),headless=True,chromium_sandbox=os.getenv('CHROMIUM_NO_SANDBOX')!='1',args=['--disable-dev-shm-usage'])
        page=await browser.new_page(viewport={'width':1440,'height':1040},device_scale_factor=1,locale='ja-JP',timezone_id='Asia/Tokyo')
        page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        if args.snapshot:
            web=source/'web'
            html=(web/'index.html').read_text().replace('<link rel="stylesheet" href="/static/app.css">','<style>'+(web/'app.css').read_text()+'</style>')
            media={name:base64.b64encode((root/name).read_bytes()).decode() for name in ['landscape.mp4','portrait.mp4','landscape.jpg','portrait.jpg']}
            script='''const FIXTURE=__FIXTURE__;
                for (const [name,data] of Object.entries(FIXTURE.media)) {
                  const bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));
                  FIXTURE.campaign.outputs[name]=URL.createObjectURL(new Blob([bytes],{type:name.endsWith('.mp4')?'video/mp4':'image/jpeg'}));
                }
                window.fetch=async (url,options={})=>{
                  const value=url==='/api/config'?FIXTURE.config:url==='/api/campaigns'?FIXTURE.campaigns:url==='/api/campaigns/'+FIXTURE.campaign.id?FIXTURE.campaign:null;
                  if(value===null)throw new Error('Snapshot harness does not perform writes/network calls: '+url);
                  return new Response(JSON.stringify(value),{status:200,headers:{'Content-Type':'application/json'}});
                };
            '''.replace('__FIXTURE__',json.dumps({'media':media,'campaign':campaign,'campaigns':campaigns,'config':config},ensure_ascii=False))
            html=html.replace('<script src="/static/app.js" type="module"></script>','<script>'+script+'</script><script type="module">'+(web/'app.js').read_text()+'</script>')
            await page.set_content(html,wait_until='load')
        else:
            await page.goto(args.base)
            await page.locator('#access-token').fill(token)
            await page.locator('#access-form button').click()
        await page.wait_for_function("() => document.getElementById('film-player')?.readyState>=1")
        await page.locator('#film-player').evaluate('(v)=>{v.preload="auto";v.load()}')
        await page.wait_for_function("() => document.getElementById('film-player')?.readyState>=2",timeout=15000)
        await page.locator('#film-player').evaluate('(v)=>{v.currentTime=4.5}')
        await page.wait_for_function("() => !document.getElementById('film-player').seeking",timeout=15000)
        await page.locator('#film-player').evaluate('async(v)=>{v.muted=true;await v.play()}')
        await page.wait_for_timeout(300)
        await page.locator('#film-player').evaluate('(v)=>v.pause()')
        await page.wait_for_timeout(200)
        report['checks']['video_frame_decoded']=True
        report['checks']['video_playback_advances']=await page.locator('#film-player').evaluate('(v)=>v.currentTime>4.5')
        report['checks']['real_video_metadata']=await page.locator('#film-player').evaluate('(v)=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration})')
        await page.screenshot(path=str(args.output/'launchloom-studio.png'),full_page=True)
        await page.click('[data-ratio="portrait"]');await page.wait_for_timeout(300)
        report['checks']['portrait_toggle']=await page.locator('.player').evaluate('(e)=>e.classList.contains("portrait")')
        await page.click('[data-tab="distribution"]')
        report['checks']['social_draft_cards']=await page.locator('[data-post]').count()
        await page.screenshot(path=str(args.output/'launchloom-distribution.png'),full_page=True)
        await page.click('[data-tab="results"]')
        report['checks']['no_invented_impressions']='SNSインプレッション：未取得' in await page.locator('#workbench').inner_text()
        await page.click('[data-tab="film"]');await page.click('[data-ratio="landscape"]')
        await page.locator('#film-player').evaluate('(v)=>{v.preload="auto";v.load();v.currentTime=4.5}')
        await page.wait_for_function("() => document.getElementById('film-player')?.readyState>=2 && !document.getElementById('film-player').seeking")
        await page.locator('#film-player').evaluate('async(v)=>{v.muted=true;await v.play()}')
        await page.wait_for_timeout(300)
        await page.locator('#film-player').evaluate('(v)=>v.pause()')
        await page.set_viewport_size({'width':390,'height':844});await page.wait_for_timeout(200)
        report['checks']['studio_mobile_no_overflow']=await page.evaluate('() => document.documentElement.scrollWidth<=innerWidth')
        await page.screenshot(path=str(args.output/'launchloom-mobile.png'),full_page=True)
        await page.click('#new-button')
        report['checks']['create_form_seven_channels']=await page.locator('input[name="channels"]').count()==7
        await page.click('[data-close="create-dialog"]')
        # Independently render the actual exported landing page, not a screenshot mock.
        if args.snapshot:
            site=root/'site';html=(site/'index.html').read_text()
            html=html.replace('<link rel="stylesheet" href="site.css">','<style>'+(site/'site.css').read_text()+'</style>')
            html=html.replace('<script src="site.js" defer></script>','<script>'+(site/'site.js').read_text()+'</script>')
            for filename,mime in [('poster.jpg','image/jpeg'),('film.mp4','video/mp4')]:
                data='data:'+mime+';base64,'+base64.b64encode((site/filename).read_bytes()).decode()
                html=html.replace('"'+filename+'"','"'+data+'"')
            await page.set_content(html,wait_until='load')
        else:await page.goto(args.base+campaign['outputs']['site/index.html'])
        await page.set_viewport_size({'width':1440,'height':1000});await page.wait_for_timeout(300)
        for y in range(0,5000,600):await page.evaluate('(y)=>scrollTo(0,y)',y);await page.wait_for_timeout(100)
        await page.evaluate('() => scrollTo(0,0)');await page.wait_for_timeout(300)
        await page.screenshot(path=str(args.output/'launchloom-landing.png'),full_page=True)
        report['checks']['landing_has_three_features']=await page.locator('.feature').count()==3
        report['checks']['landing_contains_video']=await page.locator('video').count()==1
        await page.locator('footer').scroll_into_view_if_needed()
        await page.locator('footer').hover()
        report['checks']['footer_responds_to_pointer']=await page.locator('footer').evaluate('(e)=>!!e.style.getPropertyValue("--mx")')
        await page.set_viewport_size({'width':390,'height':844});await page.evaluate('() => scrollTo(0,0)');await page.wait_for_timeout(300)
        report['checks']['landing_mobile_no_overflow']=await page.evaluate('() => document.documentElement.scrollWidth<=innerWidth')
        await page.screenshot(path=str(args.output/'launchloom-landing-mobile.png'),full_page=True)
        await browser.close()
    (args.output/'browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['page_errors'] or any(v is False for v in report['checks'].values()):raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path('.launchloom'));parser.add_argument('--output',type=Path,default=Path('checks'));parser.add_argument('--base',default='http://127.0.0.1:8787');parser.add_argument('--snapshot',action='store_true');asyncio.run(main(parser.parse_args()))
