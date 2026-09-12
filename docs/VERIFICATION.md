# Verification — 2026-09-12 JST

## Executed

| Layer | Result | Evidence |
|---|---|---|
| Python tests | **66 passed**, 0 failed | verification/pytest.xml |
| Python import/compile | Passed | python -m compileall -q launchloom |
| Browser JavaScript syntax | Passed | node --check launchloom/web/app.js |
| Package build | Python wheel built without fetching dependencies | setuptools / pip wheel --no-deps --no-build-isolation |
| Real local production | Bundled Orbit application interacted with, recorded, composed and packaged | verification/artifact-report.json |
| Landscape film | 1280×720 / H.264 / 24fps / **16.875s** | landscape.mp4, full FFmpeg decode passed |
| Portrait film | 720×1280 / H.264 / 24fps / **16.875s** | portrait.mp4, full FFmpeg decode passed |
| Landing page | Actual exported HTML/CSS/JS, 3 features, video, pointer-reactive footer | verification/browser-report.json |
| Browser component checks | Film decoded and played; aspect switch, 3 post drafts, 7 selectable channels, no page errors | verification/browser-report.json |
| Mobile layout | Studio and LP at 390px: no horizontal overflow | Browser component checks |
| Export | ZIP integrity; all manifest hashes; no raw captures/input/evidence notes | verification/artifact-report.json |
| Artifact authorization | Authenticated kit retrieval succeeds; unauthenticated media request returns 401 | Artifact report + API tests |
| External publication | **None**; no publication records in the delivered demo campaign | Artifact report |

The sample clip length is the recorded operation time plus the opening and closing,
not the time it takes to generate a clip. Render speed has not been benchmarked
across machines. Both sample videos are intentionally **silent** because no audio
asset was supplied. They show the bundled real Orbit demo app, not Astra or any
of the user's existing products. They do not use media from the reference posts.

## What “browser checked” means here

The execution environment's managed Chromium **blocks URL navigation**, including
localhost. That administrative URL policy was not changed. The real bundled app
was loaded from its owned HTML/CSS/JS into an offline browser page. Its buttons,
input, task completion and focus mode actually ran; Playwright recorded the page.
The footage was then processed by the normal renderer and packaged by the normal
persistent API worker.

UI/layout tests used actual API snapshots and the actual generated media loaded
in memory, not invented metrics or pre-drawn interface screenshots. They executed
the real front-end JavaScript and proved decoding/playback, layout and component
behavior. They **do not prove browser network, cookie/CSP integration, external URL
capture or the native screen-share permission flow**. Backend authorization/CSRF
and API logic were tested independently with FastAPI TestClient and local HTTP.

Reproduce the component checks after generating a sample:

```bash
# A normal machine can omit --snapshot for a live browser test.
python examples/verify_ui.py --data .launchloom --output checks --snapshot
```

The verification machine is Linux / Python 3.13.5 / system Chromium / FFmpeg 7.1.5.
It runs as root, so this isolated trusted sample used explicit no-sandbox mode.
Production defaults retain Chromium sandbox. The Playwright FFmpeg executable was
provided from the installed system FFmpeg in the test runtime; no browser, FFmpeg
or font binary is included in the delivered source archive.

## External integrations: implementation versus validation

| Integration | Implemented | Tested this time |
|---|---|---|
| Postiz | Integration list, upload, post/schedule request, receipt, analytics | HTTP contract mocks, validation, approval/hash/state tests; **no live account** |
| fal | Queue submit, durable ticket, poll, bounded download, uncertain-submit guard | HTTP contract mocks; **no paid video request** |
| ComfyUI | API workflow, prompt ID, history, video output download | HTTP contract mocks; **no model/custom-node execution** |
| LLM | Configured Chat Completions-compatible planning, canonical claims retained | HTTP contract mock; **no external LLM invocation** |
| Screen recording | Browser permission flow, upload, WebM duration normalization | Real synthetic stream-format file normalized; **no macOS/Windows screen-share test** |
| Staging URL capture | Explicit origin allowlist, action DSL, new context, masking | Validation/unit tests; **live navigation not tested in restricted browser** |

Other unvalidated/unimplemented work: hosted multi-user deployment, real SNS
publication state reconciliation UI, native cursor-event capture, video narration
or music generation, arbitrary AI-generated application/LP code, automatic hosting
deployment, statistical A/B optimization and continuous autonomous social growth.
Docker configuration is supplied but its image was not built in this network-
restricted environment. macOS/Windows instructions are unverified on real devices.

## Issues caught and corrected

Retry options now compare decoded JSON, avoiding integer 0 versus float 0.0 failures.
Invalid media receives a controlled 422 response rather than an unhandled exception.
Durationless browser WebM recordings are normalized before validation.
Mobile grid/video intrinsic widths no longer widen the studio beyond its viewport.
Generated-media downloads are installed only after validation, not exposed as partial
successful files. Public kits omit private feature-evidence notes and raw captures.

These tests are not a penetration test, legal/license clearance, factual audit of
operator claims, aesthetic evaluation, virality prediction or sales guarantee.
