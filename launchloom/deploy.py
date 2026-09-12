"""Publish a finished landing page into a directory the operator owns.

Deployment is deliberately boring: it copies the five generated site files into a
directory the operator configured, and nothing else. It never deletes, never
writes outside that directory, and never runs before the exact bytes have been
previewed and approved by fingerprint.

Hosted provider APIs (Netlify, Cloudflare Pages and friends) are not implemented.
A directory is enough for any static host that publishes from a folder or a repo,
and it is the only target that can be verified without someone's credentials.
"""
from __future__ import annotations
import os
import shutil
from pathlib import Path
from .config import Settings
from .security import digest, file_sha

SITE_FILES = ("index.html", "site.css", "site.js", "film.mp4", "poster.jpg")


def resolve_target(settings: Settings) -> Path:
    if not settings.deploy_dir:
        raise ValueError("Set SITE_DEPLOY_DIR to a directory you publish from")
    target = Path(os.path.expanduser(settings.deploy_dir)).resolve()
    if not target.is_dir():
        raise ValueError("SITE_DEPLOY_DIR must be an existing directory you created deliberately")
    if Path(settings.deploy_dir).is_symlink():
        raise ValueError("SITE_DEPLOY_DIR must not be a symlink")
    data = settings.data_dir.resolve()
    package = Path(__file__).resolve().parent
    for reserved, why in ((data, "the studio's own data directory"), (package, "the installed package")):
        if target == reserved or target.is_relative_to(reserved) or reserved.is_relative_to(target):
            raise ValueError(f"SITE_DEPLOY_DIR overlaps {why}")
    if target == Path.home().resolve() or target == Path(target.anchor):
        raise ValueError("Choose a dedicated directory, not a home or filesystem root")
    return target


def plan(root: Path, settings: Settings) -> dict:
    """What a deploy would write, and what is already there. Reads only."""
    target = resolve_target(settings)
    site = root / "site"
    files = []
    for name in SITE_FILES:
        source = site / name
        if not source.is_file():
            raise ValueError(f"The landing page is missing {name}; finish the campaign first")
        destination = target / name
        if destination.is_symlink():
            raise ValueError(f"{name} in the target directory is a symlink; deployment refuses to write through it")
        existing = file_sha(destination) if destination.is_file() else ""
        checksum = file_sha(source)
        files.append({"name": name, "bytes": source.stat().st_size, "sha256": checksum,
                      "status": "unchanged" if existing == checksum else "replaces" if existing else "adds"})
    untouched = sorted(p.name for p in target.iterdir() if p.name not in SITE_FILES)
    return {"target": str(target), "files": files, "left_untouched": untouched[:50],
            "fingerprint": digest({"target": str(target), "files": {f["name"]: f["sha256"] for f in files}}),
            "note": "Only these file names are written. Nothing in the target directory is deleted."}


def publish(root: Path, settings: Settings, fingerprint: str) -> dict:
    """Copy the approved bytes. The fingerprint must still describe what is on disk."""
    current = plan(root, settings)
    if fingerprint != current["fingerprint"]:
        raise ValueError("The landing page changed since it was previewed. Review the new preview and approve again.")
    target = Path(current["target"])
    written = []
    for name in SITE_FILES:
        source = root / "site" / name
        temporary = target / (name + ".launchloom-partial")
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, target / name)
        finally:
            temporary.unlink(missing_ok=True)
        written.append(name)
    return {"target": str(target), "written": written, "fingerprint": fingerprint,
            "note": "Files are in place. Serving them is your hosting's job; Launchloom does not upload or configure DNS."}
