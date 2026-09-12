"""One command that proves whether Launchloom works on this machine.

`python -m launchloom selftest` checks the environment, produces a real launch kit
from the bundled sample, inspects what came out, and writes a report the operator
can paste into an issue without having to describe anything themselves.

It runs the actual pipeline — not a simulation of it — in a temporary directory,
and touches nothing else. No network, no account, no API key.
"""
from __future__ import annotations
import asyncio
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from . import __version__
from .config import Settings
from .models import BuildOptions
from .store import Store

PRIVATE = ("capture/", "input/", ".render.log", ".partial", "brief.json", "review-frame.jpg")


def version_of(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        return "MISSING"
    try:
        first = subprocess.run([binary, "-version"], capture_output=True, text=True, timeout=20).stdout.splitlines()
        return first[0][:90] if first else path
    except Exception:
        return path


def decodes(path: Path) -> bool:
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
                          capture_output=True).returncode == 0


def environment(settings: Settings) -> dict:
    from .capture import browser_status
    from .rendering import font_source
    browser, ready, problem = browser_status(settings)
    text_font, text_cjk = font_source(False)
    bold_font, bold_cjk = font_source(True)
    import importlib.metadata
    return {
        "launchloom": __version__,
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python": sys.version.split()[0],
        "ffmpeg": version_of("ffmpeg"),
        "ffprobe": "present" if shutil.which("ffprobe") else "MISSING",
        "browser": browser or "not resolved",
        "browser_launches": ready,
        "browser_problem": problem,
        "chromium_sandbox": not settings.no_sandbox,
        "text_font": text_font or "Pillow built-in",
        "bold_font": bold_font or "Pillow built-in",
        "fonts_cover_japanese": text_cjk and bold_cjk,
        "packages": {name: importlib.metadata.version(name) for name in
                     ("fastapi", "playwright", "Pillow", "pydantic", "numpy")},
    }


def inspect(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text())
    with zipfile.ZipFile(root / "launch-kit.zip") as archive:
        names = archive.namelist()
        integrity = archive.testzip() is None
    from .security import file_sha
    return {
        "landscape": manifest["videos"]["landscape"],
        "portrait": manifest["videos"]["portrait"],
        "kit_entries": len(names),
        "checks": {
            "landscape_decodes": decodes(root / "landscape.mp4"),
            "portrait_decodes": decodes(root / "portrait.mp4"),
            "zip_intact": integrity,
            "manifest_hashes_match": all(file_sha(root / name) == entry["sha256"]
                                         for name, entry in manifest["files"].items()),
            "no_raw_capture_in_kit": not any(any(p in name for p in PRIVATE) for name in names),
            "landing_page_written": (root / "site" / "index.html").is_file(),
            "captions_written": (root / "captions.srt").is_file(),
            "posts_written": (root / "posts.json").is_file(),
        },
    }


def run(settings: Settings | None = None, keep: Path | None = None) -> dict:
    """Build the bundled sample end to end and report what happened."""
    from .pipeline import SAMPLES, build

    started = time.monotonic()
    workspace = Path(tempfile.mkdtemp(prefix="launchloom-selftest-"))
    report: dict = {"environment": environment(settings or Settings()), "build": {}}
    try:
        scratch = Settings(data_dir=workspace, token="selftest-token-with-enough-characters")
        scratch.prepare()
        store = Store(scratch.data_dir / "launchloom.sqlite3")
        # Always the English sample, so two reports from two machines are comparable.
        campaign = store.create_campaign(SAMPLES["en"])
        options = BuildOptions(capture_mode="sample", quality="draft")
        asyncio.run(build(scratch, store, campaign["id"], options))
        root = scratch.data_dir / "campaigns" / campaign["id"]
        report["build"] = {"ok": True, "seconds": round(time.monotonic() - started, 1), **inspect(root)}
        if keep:
            keep.mkdir(parents=True, exist_ok=True)
            for name in ("landscape.mp4", "portrait.mp4", "launch-kit.zip"):
                shutil.copy(root / name, keep / name)
            report["build"]["kept_in"] = str(keep)
    except Exception as error:
        report["build"] = {"ok": False, "seconds": round(time.monotonic() - started, 1),
                           "error": f"{type(error).__name__}: {error}"[:600]}
    finally:
        if not keep:
            shutil.rmtree(workspace, ignore_errors=True)
    return report


def render_report(report: dict) -> str:
    environment_lines = "\n".join(f"  {key}: {value}" for key, value in report["environment"].items()
                                  if key != "packages")
    packages = "  packages: " + ", ".join(f"{n} {v}" for n, v in report["environment"]["packages"].items())
    build = report["build"]
    if build.get("ok"):
        checks = "\n".join(f"  {'PASS' if value else 'FAIL'}  {name}"
                           for name, value in build["checks"].items())
        outcome = (f"  built in {build['seconds']}s\n"
                   f"  landscape: {build['landscape']['width']}x{build['landscape']['height']}"
                   f" {build['landscape']['duration']}s {build['landscape']['bytes']} bytes\n"
                   f"  portrait:  {build['portrait']['width']}x{build['portrait']['height']}"
                   f" {build['portrait']['duration']}s {build['portrait']['bytes']} bytes\n"
                   f"  kit entries: {build['kit_entries']}\n{checks}")
    else:
        outcome = f"  FAILED after {build['seconds']}s\n  {build.get('error', 'unknown error')}"
    return (f"Launchloom selftest\n\nEnvironment\n{environment_lines}\n{packages}\n\nBuild\n{outcome}\n")


def main(settings: Settings, keep: Path | None = None) -> int:
    print("Running the bundled sample through the real pipeline. This takes about half a minute.\n",
          flush=True)
    report = run(settings, keep)
    text = render_report(report)
    print(text)
    destination = Path("launchloom-selftest.txt")
    destination.write_text(text)
    json_destination = Path("launchloom-selftest.json")
    json_destination.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    passed = report["build"].get("ok") and all(report["build"].get("checks", {}).values())
    print(f"Written to {destination} and {json_destination}.")
    if passed:
        print("\nEverything passed. If you are willing, paste that file into\n"
              "https://github.com/FORIFOR/Launchloom/issues/new?template=tester-report.yml\n"
              "— knowing it works on a machine that is not mine is the most useful thing anyone can send.")
    else:
        print("\nSomething failed, which is worth more to me than a pass. Please paste that file into\n"
              "https://github.com/FORIFOR/Launchloom/issues/new?template=tester-report.yml")
    return 0 if passed else 1
