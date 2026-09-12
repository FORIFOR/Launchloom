"""Check what a finished campaign actually produced, and what it kept private.

Run it against a running studio after a build:

    python examples/verify_artifacts.py --data .launchloom --output docs/verification

It re-derives every claim from files on disk and from the HTTP API, so the report
is reproducible rather than something written once and shipped.
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import zipfile
from pathlib import Path
import httpx

PRIVATE = ("capture/", "input/", ".render.log", ".partial", "brief.json", "review-frame.jpg")


def decodes(path: Path) -> bool:
    """Decode every frame, not just read the header: a file can probe fine and
    still be truncated."""
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
                          capture_output=True).returncode == 0


def main(args):
    token = (args.data / "access-token").read_text().strip()
    with httpx.Client(base_url=args.base, headers={"Authorization": "Bearer " + token}, timeout=60) as client:
        campaigns = client.get("/api/campaigns").json()
        ready = [c for c in campaigns if c["state"] == "ready"]
        if not ready:
            sys.exit("No finished campaign to check. Build one first.")
        campaign = client.get("/api/campaigns/" + ready[0]["id"]).json()
        cid = campaign["id"]
        root = args.data / "campaigns" / cid
        manifest = json.loads((root / "manifest.json").read_text())
        kit = client.get(f"/artifacts/{cid}/launch-kit.zip")
        anonymous = httpx.get(args.base + f"/artifacts/{cid}/landscape.mp4")
        config = client.get("/api/config").json()

    with zipfile.ZipFile(root / "launch-kit.zip") as archive:
        names = archive.namelist()
        integrity = archive.testzip() is None
        exported = archive.read("campaign.json").decode()

    evidence = [f["evidence"] for f in campaign["brief"]["features"] if f.get("evidence")]
    report = {
        "campaign_id": cid,
        "revision": manifest.get("revision", 0),
        "checks": {
            "campaign_ready": campaign["state"] == "ready",
            "zip_integrity": integrity,
            "all_manifest_hashes_match": all((root / name).is_file() for name in manifest["files"]),
            "no_raw_capture_or_input": not any(any(p in name for p in PRIVATE) for name in names),
            "private_evidence_not_exported": all(note not in exported for note in evidence),
            "landscape_full_decode": decodes(root / "landscape.mp4"),
            "portrait_full_decode": decodes(root / "portrait.mp4"),
            "no_publication_records": not campaign["publications"],
            "authenticated_kit_download": kit.status_code == 200,
            "unauthenticated_artifacts_blocked": anonymous.status_code == 401,
            "live_publish_disabled": not config["live_publish"],
        },
        "videos": manifest["videos"],
        "provenance": manifest["provenance"],
        "python": sys.version.split()[0],
        "ffmpeg": subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.splitlines()[0],
    }
    from launchloom.security import file_sha
    report["checks"]["all_manifest_hashes_match"] = all(
        file_sha(root / name) == entry["sha256"] for name, entry in manifest["files"].items())

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "artifact-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not all(report["checks"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path(".launchloom"))
    parser.add_argument("--output", type=Path, default=Path("checks"))
    parser.add_argument("--base", default="http://127.0.0.1:8787")
    main(parser.parse_args())
