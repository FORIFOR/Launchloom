from __future__ import annotations
import asyncio
import json
import time
from pathlib import Path
from playwright.async_api import async_playwright
from .config import Settings
from .models import BuildOptions, CaptureStep
from .security import origin, check_capture_url

SAMPLE_STEPS=[
    CaptureStep(action='fill',selector='#new-task',value='Launch the next good idea',label='思いついた瞬間に、書き留める。',milliseconds=1300),
    CaptureStep(action='click',selector='#add-task',label='ひとつの場所に、まとめる。',milliseconds=1300),
    CaptureStep(action='click',selector='[data-task="0"]',label='終わったことを、気持ちよく。',milliseconds=1200),
    CaptureStep(action='click',selector='#focus-button',label='次の一歩だけに、集中する。',milliseconds=1800)
]

MISSING_BROWSER=("Chromium is not installed for this Playwright version. Run "
    "`python -m playwright install chromium`, or set CHROMIUM_EXECUTABLE to an existing browser.")

def browser_status(settings: Settings) -> tuple[str,bool,str]:
    """Launch the browser once. Checking a path is not enough: the headless shell
    is a separate download from the full Chromium build."""
    from playwright.sync_api import sync_playwright
    path=settings.chromium or ''
    try:
        with sync_playwright() as p:
            path=settings.chromium or p.chromium.executable_path
            browser=p.chromium.launch(executable_path=settings.chromium,headless=True,
                chromium_sandbox=not settings.no_sandbox,args=['--disable-dev-shm-usage'])
            browser.close()
        return path,True,''
    except Exception as e:
        text=str(e)
        if "Executable doesn't exist" in text or 'playwright install' in text:
            return path,False,MISSING_BROWSER
        return path,False,text.strip().splitlines()[0][:200]

async def launch_chromium(playwright,settings: Settings):
    """Fail with an actionable message instead of Playwright's install banner."""
    try:
        return await playwright.chromium.launch(executable_path=settings.chromium,headless=True,
            chromium_sandbox=not settings.no_sandbox,args=['--disable-dev-shm-usage'])
    except Exception as e:
        text=str(e)
        if "Executable doesn't exist" in text or 'playwright install' in text:
            raise ValueError(MISSING_BROWSER) from e
        raise


async def capture(settings: Settings,options: BuildOptions,dest: Path) -> dict:
    url=settings.base_url+'/demo-app' if options.capture_mode=='sample' else options.capture_url
    studio_origin=origin(settings.base_url)
    allowed={origin(u.strip()) for u in settings.capture_origins.split(',') if u.strip()}
    if options.capture_mode=='sample':allowed.add(studio_origin)
    await asyncio.to_thread(check_capture_url,url,allowed,studio_origin)
    steps=SAMPLE_STEPS if options.capture_mode=='sample' else options.steps
    dest.mkdir(parents=True,exist_ok=True)
    events=[]
    async with async_playwright() as p:
        browser=await launch_chromium(p,settings)
        context=await browser.new_context(viewport={'width':1280,'height':800},
            record_video_dir=str(dest),record_video_size={'width':1280,'height':800},
            accept_downloads=False,service_workers='block')
        try:
            async def guard(route):
                try:
                    if route.request.url.startswith('data:'):return await route.continue_()
                    await asyncio.to_thread(check_capture_url,route.request.url,allowed,studio_origin)
                    if route.request.method not in {'GET','HEAD','OPTIONS'} and not options.allow_site_writes:
                        return await route.abort()
                    await route.continue_()
                except Exception:await route.abort()
            await context.route('**/*',guard)
            await context.route_web_socket('**/*',lambda ws:ws.close())
            redactions=options.redact_selectors+['input[type="password"]','[data-private]']
            # Apply DOM redaction before interactions. Canvas/video and all possible first-paint races are not covered.
            await context.add_init_script('''(() => {
              const selectors = '''+json.dumps(redactions)+''';
              const hide = () => {for(const s of selectors){try{for(const e of document.querySelectorAll(s)){e.style.setProperty('visibility','hidden','important');}}catch{}}};
              new MutationObserver(hide).observe(document,{childList:true,subtree:true,attributes:true,attributeFilter:['value','type','data-private']});
              document.addEventListener('DOMContentLoaded',hide);
            })();''')
            page=await context.new_page();started=time.monotonic()
            if options.capture_mode=='sample':
                # The bundled sample is a real, interactive application. Load its owned
                # sources offline: no network navigation, credentials or website access.
                web=Path(__file__).parent/'web'
                html=(web/'demo-app.html').read_text()
                html=html.replace('<link rel="stylesheet" href="/demo-assets/demo-app.css">', '<style>'+(web/'demo-app.css').read_text()+'</style>')
                html=html.replace('<script src="/demo-assets/demo-app.js"></script>', '<script>'+(web/'demo-app.js').read_text()+'</script>')
                await page.set_content(html,wait_until='domcontentloaded')
            else:
                await page.goto(url,wait_until='domcontentloaded',timeout=30000)
            await page.wait_for_timeout(700)
            await page.evaluate('''() => {
                const c=document.createElement('div');c.id='launchloom-cursor';c.style.cssText='position:fixed;left:0;top:0;width:18px;height:18px;border:3px solid #fff;border-radius:50%;background:#ed6847;box-shadow:0 1px 8px #0008;z-index:2147483647;pointer-events:none;transition:transform .24s ease';document.body.append(c);
                document.addEventListener('mousemove',e=>c.style.transform=`translate(${e.clientX-9}px,${e.clientY-9}px)`);
            }''')
            for step in steps:
                point={'x':0.5,'y':0.5}
                if step.action in {'fill','click'}:
                    el=page.locator(step.selector).first
                    await el.wait_for(state='visible',timeout=8000)
                    box=await el.bounding_box()
                    if box:
                        x=box['x']+box['width']/2;y=box['y']+box['height']/2
                        point={'x':x/1280,'y':y/800}
                        await page.mouse.move(x,y,steps=12)
                    if step.action=='fill':await el.fill(step.value)
                    else:await el.click(timeout=5000)
                elif step.action=='scroll':await page.mouse.wheel(0,step.delta_y)
                events.append({'time':round(time.monotonic()-started,3),'label':step.label,'action':step.action,**point})
                await page.wait_for_timeout(step.milliseconds)
            await page.wait_for_timeout(600)
            await page.screenshot(path=str(dest/'screen.png'))
            video=page.video
            await context.close()
            await video.save_as(str(dest/'capture.webm'))
            result={'video':'capture.webm','width':1280,'height':800,'events':events,'source_url':'bundled:demo-app' if options.capture_mode=='sample' else url,'redactions':redactions,'timing_note':'Event timestamps are approximate relative to browser-page creation.'}
            (dest/'events.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
            # Playwright's randomly named intermediate is not an output asset.
            for f in dest.glob('*.webm'):
                if f.name!='capture.webm':f.unlink(missing_ok=True)
            return result
        finally:
            await browser.close()
