# Local application distribution candidate

2026-10-04. This is a packaging and installation record, not a released paid
edition or a claim that every buyer's machine is supported.

## What can be sold

Apache-2.0 permits distributing the application for a fee and offering optional
installation/support. Preserve the license, applicable notices and change
attribution. Existing Apache-covered code remains available under its license;
charging for the package does not make it exclusively proprietary. Support or
warranty commitments are the seller's own. See [LICENSE](../LICENSE), especially
sections 4 and 9, and [the authoritative Apache text](https://www.apache.org/licenses/LICENSE-2.0).

The smallest candidate is the application wheel, this guide, LICENSE, NOTICE,
THIRD_PARTY.md, the exact source commit and artifact checksum. Its bundled Orbit
sample is local HTML/CSS/JS and is silent unless the operator supplies audio.
Install Python/native dependencies separately from their maintained upstream
sources. An optional fixed installation covers one agreed machine and the
acceptance steps below; its price and support terms have not been set here.

Do not put an existing virtual environment, Chromium, FFmpeg, OS fonts, narrated
homepage films or historic example kits into that package without inventorying
their exact licenses and redistribution rights. In particular, the music and
narration grants for homepage/intro*.mp4 and homepage/ja/intro*.mp4 were not
established by this check. The source-only wheel excludes them. A self-contained
installer or container has additional obligations described in
[THIRD_PARTY.md](../THIRD_PARTY.md) and [FFmpeg's official guidance](https://ffmpeg.org/legal.html).

This candidate covers one trusted local operator importing their own recording,
reviewing the plan and exporting a launch kit. Accounts/team operation, managed
hosting, paid AI, publication services and recurring support are separate scopes.

## Reproducible installation and buyer acceptance

Seller preparation: build the wheel from the reviewed commit, record that commit
in SOURCE_COMMIT.txt, and record the wheel's SHA-256 in SHA256SUMS. Do not identify
a development checkout only by version 0.1.2: several commits share that version.
Keep the source and package notices together. The commands below assume that
wheel and its notices have already been supplied; no paid release URL exists yet.

Prerequisites: Python 3.11 or later (this run used 3.12.14), FFmpeg/ffprobe with
libx264, readable Japanese/Latin fonts, a supported local browser, and writable
disk space for the input, two videos and a ZIP. Recording the bundled app or a
staging site additionally needs the Playwright Chromium installation and its OS
libraries. An import-only film does not use browser capture.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./launchloom-0.1.2-py3-none-any.whl
python -m pip check
ffmpeg -version
ffprobe -version
ffmpeg -hide_banner -encoders
# Confirm libx264 appears above; install OS dependencies before continuing.
python -m playwright install chromium
python -m launchloom doctor
python -m launchloom serve
```

Windows uses `.venv\Scripts\Activate.ps1` instead of the activation command above;
Windows was not validated here. For macOS/Linux prerequisite instructions, see
[README.ja.md](../README.ja.md#いちばん早い試し方). Do not treat paths merely existing
as a successful doctor result: read browser launch and font coverage separately.
Do not disable browser security to make an unsupported machine pass acceptance.

Open the loopback address printed by the server (normally
http://127.0.0.1:8787), and enter its local access key. Keep the server terminal
open. From the ordinary studio:

1. Create a campaign with accurate product claims and a recording you may use.
   Choose imported footage, local rendering and review before rendering. Leave
   paid provider and publishing integrations disabled.
2. Import the recording and start the build. Confirm it stops for review before
   creating either finished MP4.
3. Change a scene headline/supporting line and an SRT caption. Save, reload the
   campaign URL, and confirm the text remains. Stop and restart the server from
   the same working directory, then confirm the same campaign and edits remain.
4. Approve rendering. Play both complete videos, check the separate captions.srt,
   and download the ZIP. Check its manifest hashes and template license notices.
   Reopen the campaign and confirm the download remains available.

Headlines/supporting lines change the video layout. SRT captions are separate
files, not burned into the MP4; text already inside an imported recording is not
editable. Standard-studio landing-page and social copy comes from the original
brief and does not automatically follow later scene edits. Read all outputs.

Data defaults to `.launchloom` beneath the directory from which the server was
started. Start from the same directory each time, or deliberately configure a
stable LAUNCHLOOM_DATA path. Before an upgrade, stop the server and back up the
whole data directory; it contains private footage, SQLite data and the local key.
Keep that backup private. Downgrading a database is not guaranteed. Record the
commit, Python/OS versions, doctor output and failing stage for support; do not
send raw customer recordings, API keys or the access-token file in a bug report.

## What this check actually established

The starting point was PR27 commit
`0994b99ba9cf728fc0e2e5fed31b91712650c06a`. All 63 source files used for the package
were checked against their Git blob hashes. The wheel was built without vendored
dependencies, installed into a new isolated venv, and imported from site-packages
outside the source checkout. Dependency resolution and pip check succeeded.

A real separate server process, accessed over its local HTTP API, passed 35
checks: packaged studio/sample assets; a fresh database and private local token;
invalid-media rejection; existing real-footage import; review stop; title/detail/
SRT save; process restart and retained edits; export; full decoding of both films;
ZIP integrity and file hashes; no raw input in the ZIP; and a second restart with
the same ready campaign and download. The 10-second draft films were 960x540 and
540x960, H.264/30fps. Rendering took 16.15 seconds of machine wait. Human setup or
support time was not measured. The earlier 26-second full-HD run is recorded in
[real-material-2026-10-04.md](quality/real-material-2026-10-04.md) and was not repeated.

Observed runtime versions: FastAPI 0.128.8, Uvicorn 0.48.0, Pydantic 2.13.5,
HTTPX 0.28.1, Pillow 12.3.0, Playwright 1.57.0, NumPy 2.5.3. These are observed
versions, not a complete reproducible dependency lock. The machine already had
FFmpeg and Noto CJK fonts. This was a clean Python installation, not a fresh OS.

The first HTTP test harness inherited this cloud environment's SOCKS proxy and
failed before requests because optional socksio was absent. The loopback-only
test client was corrected to ignore proxy environment variables; the application
was unchanged. This was a test-harness issue, not a product install failure.

During distribution review, template LICENSE/NOTICE propagation was missing from
generated sites/ZIPs. The accompanying fix adds scoped notices to the package and
exports. The fixed wheel was installed over only the application in the same
isolated dependency environment, then run with another empty data directory.
All 39 HTTP/process/export checks passed, including exact notices at both ZIP
root and site/, matching hashes and authenticated notice downloads. The final
10-second draft render took 15.81 seconds; the ZIP has 20 members. The installed
wheel SHA-256 was
`443f30cee8f0ffe318bda5d77a6e61502a0c465b01f02be53c8b7e3a0b34025e`.
The available local suite passed 134 tests and 44 subtests. Its one initial
failure was a missing issue-template file in this partial source checkout;
fetching the unchanged committed file and rerunning that check passed.
Full-repository CI is reported separately for the final PR head. Earlier 16-file kits
do not retroactively acquire those files. Regenerate an old campaign with this
version before using its directory-deployment path. A preview missing notices
fails with that instruction and does not silently rewrite the old campaign.

## Remaining release gates

- A purchase-ready, immutable artifact with its exact commit/checksum and a
  declared supported OS has not been published.
- A new buyer's macOS/Windows installation, OS prerequisite installation,
  browser interaction, capture permissions and bundled-app recording were not
  exercised in this cloud pass. Existing browser restrictions were not bypassed.
- Run the acceptance above on the first supported buyer-equivalent machine,
  including actual playback, file saving and reopening. Record hands-on setup and
  support time before promising a fixed low-support self-service product.
- A bundled-native-binary release additionally needs exact component notices and
  corresponding-source fulfillment; a full-repository media package needs asset
  grants. Neither is implied by successful application tests.

Verdict: the local import/export application has concrete functioning-package
evidence and can be prepared as a narrowly described paid developer preview with
optional installation. General-consumer, turnkey self-service distribution is
not established by this run. The missing evidence is installation/support and
distribution acceptance, not a claim that the verified pipeline is broken.
