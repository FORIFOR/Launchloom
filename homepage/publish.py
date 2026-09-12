"""Publish homepage/ to the gh-pages branch.

    python homepage/publish.py

Builds a commit containing exactly the contents of this folder and moves
gh-pages to it. The working tree is never touched: the commit is assembled with
a temporary index, so an unfinished change on your current branch cannot be
published by accident.
"""
from __future__ import annotations
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOMEPAGE = Path(__file__).resolve().parent
ROOT = HOMEPAGE.parent
SKIP = {"README.md", "publish.py", "check.py", "__pycache__"}


def git(*args, **kwargs):
    result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, **kwargs)
    if result.returncode:
        sys.exit(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def main():
    files = sorted(p for p in HOMEPAGE.iterdir() if p.is_file() and p.name not in SKIP)
    if not any(p.name == "index.html" for p in files):
        sys.exit("homepage/index.html is missing")

    with tempfile.TemporaryDirectory() as scratch:
        environment = {**os.environ, "GIT_INDEX_FILE": str(Path(scratch) / "index")}
        for path in files:
            blob = subprocess.run(["git", "-C", str(ROOT), "hash-object", "-w", str(path)],
                                  capture_output=True, text=True, check=True).stdout.strip()
            subprocess.run(["git", "-C", str(ROOT), "update-index", "--add", "--cacheinfo",
                            f"100644,{blob},{path.name}"], env=environment, check=True)
        tree = subprocess.run(["git", "-C", str(ROOT), "write-tree"], env=environment,
                              capture_output=True, text=True, check=True).stdout.strip()

    parents = []
    existing = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", "-q", "refs/heads/gh-pages"],
                              capture_output=True, text=True)
    if existing.returncode == 0:
        parents = ["-p", existing.stdout.strip()]
    source = git("rev-parse", "--short", "HEAD")
    commit = git("commit-tree", tree, *parents, "-m", f"Publish homepage from {source}")
    git("update-ref", "refs/heads/gh-pages", commit)

    print(f"gh-pages -> {commit[:10]} ({len(files)} files)")
    print("Push it with:  git push origin gh-pages")


if __name__ == "__main__":
    main()
