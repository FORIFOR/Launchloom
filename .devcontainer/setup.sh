#!/usr/bin/env bash
# Everything a Codespace needs to run Launchloom. Chromium and FFmpeg come from
# Debian; Playwright's own FFmpeg is a separate binary it uses for recording, so
# both are installed.
set -euo pipefail

# The base image carries a third-party yarn source whose signing key has expired,
# which makes apt-get update exit non-zero even though Debian's own lists updated
# fine. Nothing here needs yarn, so the failure is tolerated and the install below
# is what actually has to succeed.
sudo apt-get update || true
sudo apt-get install -y --no-install-recommends \
  ffmpeg chromium chromium-sandbox fonts-noto-cjk

python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m playwright install ffmpeg

cat <<'NOTE'

Ready. Two things worth running:

  CHROMIUM_NO_SANDBOX=1 python -m launchloom selftest
      Builds a real launch kit from the bundled sample and checks what came out.
      About twenty seconds. It writes launchloom-selftest.txt — that file is the
      whole report, and pasting it into an issue is the entire ask:
      https://github.com/FORIFOR/Launchloom/issues/2

  python -m launchloom serve
      The studio itself, on the forwarded port 8787.

Why the flag: a Codespace runs under a seccomp profile that blocks the
user-namespace syscalls Chromium's sandbox needs, and unlike docker compose there
is no way to supply a different one. Without the flag the browser will not launch
at all. It is acceptable for the bundled sample, which only ever loads HTML from
this repository, in a container you are about to throw away. If you go on to
record something of your own here, know that you are doing it with Chromium's own
sandbox off.
NOTE
