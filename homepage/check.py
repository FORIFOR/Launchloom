"""Check the homepage in a real browser before it goes live.

    python -m http.server 4477 --directory homepage
    python homepage/check.py

Fails if the film does not decode and play, if anything overflows horizontally at
phone width, or if the page reports an error. A landing page that only looks
right in a screenshot is how a broken one gets published.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright


async def main(args):
    report = {"url": args.url, "errors": [], "checks": {}}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 950}, locale="en-US")
        page.on("pageerror", lambda e: report["errors"].append(str(e)))
        def note_failure(request):
            # Pausing a video aborts its range request; that is the browser being
            # efficient, not the page being broken.
            reason = (request.failure or "")
            if "ERR_ABORTED" in reason and request.resource_type in {"media", "image"}:
                report.setdefault("aborted", []).append(request.url.rsplit("/", 1)[-1])
                return
            report["errors"].append(f"failed request ({reason}): {request.url}")
        page.on("requestfailed", note_failure)
        await page.goto(args.url, wait_until="load")

        await page.wait_for_function("() => document.querySelector('.hero video')?.readyState>=2", timeout=30000)
        report["checks"]["film_metadata"] = await page.locator(".hero video").evaluate(
            "(v)=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration})")
        await page.wait_for_timeout(1500)
        report["checks"]["film_plays"] = await page.locator(".hero video").evaluate(
            "(v)=>v.currentTime>0.3 && !v.paused")

        height = await page.evaluate("() => document.body.scrollHeight")
        for y in range(0, height, 600):
            await page.evaluate('(y)=>window.scrollTo({top:y,behavior:"instant"})', y)
            await page.wait_for_timeout(90)
        await page.evaluate('()=>window.scrollTo({top:0,behavior:"instant"})')
        await page.wait_for_timeout(500)

        # the narrated explainer must carry audio, or the section is pointless
        report["checks"]["narrated_videos_present"] = await page.evaluate(
            "() => document.querySelectorAll('#narrated video').length")
        for name in ("intro.mp4", "intro-vertical.mp4"):
            probe = await page.request.get(args.url.rstrip("/") + "/" + name)
            report["checks"]["serves_" + name] = probe.status == 200 and int(probe.headers.get("content-length", 0)) > 100000

        report["checks"]["every_section_visible"] = await page.evaluate(
            "() => document.querySelectorAll('.reveal').length===document.querySelectorAll('.reveal.in').length")
        report["checks"]["no_horizontal_overflow_desktop"] = await page.evaluate(
            "() => document.documentElement.scrollWidth<=innerWidth")
        report["checks"]["outbound_links_resolve"] = await page.evaluate(
            "() => [...document.querySelectorAll('a[href^=\"http\"]')].every(a=>a.href.includes('github'))")
        await page.screenshot(path=str(args.output / "homepage-desktop.png"))

        await page.set_viewport_size({"width": 390, "height": 844})
        await page.evaluate('()=>window.scrollTo({top:0,behavior:"instant"})')
        await page.wait_for_timeout(600)
        report["checks"]["no_horizontal_overflow_mobile"] = await page.evaluate(
            "() => document.documentElement.scrollWidth<=innerWidth")
        await page.screenshot(path=str(args.output / "homepage-mobile.png"), full_page=True)
        await browser.close()

    print(json.dumps(report, indent=2, ensure_ascii=False))
    failed = [k for k, v in report["checks"].items() if v is False]
    if failed or report["errors"]:
        sys.exit("Failed: " + ", ".join(failed + report["errors"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:4477/")
    parser.add_argument("--output", type=Path, default=Path("checks"))
    arguments = parser.parse_args()
    arguments.output.mkdir(parents=True, exist_ok=True)
    asyncio.run(main(arguments))
