# Verification

What was actually executed, on which machine, and what remains untested.
Every row below can be reproduced from a clone; nothing here is a screenshot
of a claim someone made earlier.

## The machine

| | |
|---|---|
| Hardware / OS | Apple Silicon Mac, macOS 26.6.2 |
| Python | 3.14.6 (Homebrew) |
| FFmpeg / ffprobe | 9.0.1 |
| Browser | Playwright-managed Chromium (build 1200), sandbox enabled |
| Fonts | Hiragino Sans W3 / W6 (resolved by `launchloom doctor`) |
| Container | Docker Desktop, image built from the bundled `Dockerfile` |

Date of this record: 2026-09-12.

## Executed

| Layer | Result | How to reproduce |
|---|---|---|
| **A stranger's first three minutes** | A clean `git clone` of the published repository, installed with the README's commands, opened in an English browser: the access dialog, the studio, all five tabs, the storyboard and the post drafts were English with no Japanese left, one click produced a real 1280×720 film in 14.5 seconds and a launch kit, and no page errored | the commands in README.md, then press *Try the sample* |
| Package build | Wheel and sdist build, the wheel installs into a clean environment, the `launchloom` console script runs, and the bundled web/template assets are inside it | `python -m build` then install the wheel |
| Continuous integration | Green on `ubuntu-latest` / Python 3.13 — the only evidence the suite passes outside this Mac and the container | `.github/workflows/check.yml` |
| English output | A brief with `language: "en"` produced an English plan, film, post copy and a landing page with `lang="en"` and no Japanese characters anywhere in it | build a campaign with `"language": "en"` |
| **English studio** | Every screen walked in an English browser — shell, all five tabs, the review gate, the create dialog in each capture mode, the connection wizard and the approval dialog — with **zero** Japanese text nodes or attributes left, and no page errors | open the studio with a non-Japanese browser locale |
| Japanese studio unchanged | The same browser checks pass with a `ja-JP` locale after the translation layer was added | `python examples/verify_ui.py` |
| **`launchloom selftest`** | The command a tester runs: drove the bundled app, rendered both cuts, wrote the page and the kit, and passed all eight output checks in 21s on this machine | `python -m launchloom selftest` |
| selftest without a browser | With `CHROMIUM_EXECUTABLE` pointed at nothing, it fell back to motion graphics in 5.5s, still produced a complete kit, and correctly reported the run as **not** a pass | `CHROMIUM_EXECUTABLE=/nonexistent python -m launchloom selftest` |
| selftest in the container | All eight checks passed inside the image with Chromium's sandbox on, and again with the single-flag `CHROMIUM_NO_SANDBOX=1` path the docs offer | `docker run … python -m launchloom selftest` |
| **The Codespaces recipe** | `.devcontainer/setup.sh` was run inside the same base image Codespaces uses (`mcr.microsoft.com/devcontainers/python:1-3.12-bookworm`). With Chromium's sandbox on, the browser would not launch at all — that runtime blocks the user-namespace syscalls it needs and offers no way to supply a different seccomp profile; with `CHROMIUM_NO_SANDBOX=1` all eight checks passed in 20.3s. The setup script says exactly this rather than setting the flag silently | `docker run … bash .devcontainer/setup.sh` |
| **The published image, both architectures** | `ghcr.io/forifor/launchloom` carries linux/amd64 and linux/arm64. CI runs the selftest inside the joined image on x86_64 before publishing; the arm64 half was then pulled and run on an Apple Silicon Mac — all eight checks passed in 21s | `docker run --rm -e CHROMIUM_NO_SANDBOX=1 ghcr.io/forifor/launchloom python -m launchloom selftest` |
| Unwritable directory | A run in a read-only directory prints the report and says nothing was saved, rather than failing | `tests/test_core.py::test_selftest_survives_a_directory_it_cannot_write` |
| Test suite | **435 passed**, 0 failed | `python -m pytest -q` |
| **Claims QA, 300 briefs** | Every claim in every surface traced back to an approved feature. 300 generated briefs — both languages, 1–8 features, every channel combination, 870 approved features, 475 deliberately withheld ones, 1,094 private evidence notes and 1,196 generated posts — with the storyboard, the posts, `social-copy.md`, the landing page and the captions all read back and searched. 0 leaks. The check was then proved capable of failing: three separate mutations to the production code (the page rendering unapproved features, an evidence note appended to a post, a proof scene rebound to an unapproved feature) failed 217, 299 and 118 of the 300 | `python -m pytest tests/test_claims.py -q` |
| Import / compile | Passed | `python -m compileall -q launchloom` |
| Studio JavaScript syntax | Passed | `node --check launchloom/web/app.js` |
| Environment readiness | Browser launches, both fonts cover Japanese | `python -m launchloom doctor` |
| Bundled sample, end to end | Recorded, rendered, packaged in ~22s | `python -m launchloom demo` |
| **Staging URL capture** | A real local app at `http://127.0.0.1:3177` was navigated, driven and recorded; `.tag` elements were masked as instructed | `examples/browser-capture.json` against your own staging origin |
| **Imported footage** | An MP4/WebM upload with an operator event track produced the same camera work and on-screen labels | Create a campaign with `capture_mode: upload` |
| Capture trimming | 12s source, 2.0s–6.0s range → 10s film instead of 18s | `tests/test_providers_and_media.py` |
| Music + narration | Both uploaded, mixed to one AAC track cut to the film's length, music held under the voice | Upload 音楽 and ナレーション on a campaign |
| **Launchloom filming itself** | The studio was recorded doing a full run in English, the recording imported back in, and the film cut by the same pipeline | `homepage/film.mp4` |
| **Narrated explainer** | The motion-graphics path with a narration track and a music bed produced a 26s film in both cuts; both decode fully, carry one AAC track, and play in a real browser from the published page | build with `capture_mode: none`, an `audio` and a `narration` upload |
| **The kit on the homepage** | The downloadable `launch-kit.zip` is the export of the campaign that produced the film shown above it: zip integrity holds, 16 entries, and no raw capture or input inside | `curl` it and open the archive |
| Homepage evidence sections | The generated landing page shown on the homepage is a screenshot of `site/index.html` from the downloadable kit, and the file excerpts beside it are copied from that kit | unzip `launch-kit.zip` and compare |
| **Both language pages** | English and Japanese pages checked separately in a real browser: film plays, both narrated cuts serve, every section renders, nothing overflows at 390px, the language switch resolves, no page errors | `python homepage/check.py --url .../` and `.../ja/` |
| **Published homepage** | Live page checked in a real browser: the film decodes and plays, no section depends on an observer firing, nothing overflows at 390px, no page errors | `python homepage/check.py --url https://forifor.github.io/Launchloom/` |
| Storyboard review gate | Build stopped after capture; scenes and captions reworded; approved; rendered with the operator's words in `captions.srt` | Tick 「レンダリング前に、構成と収録内容を確認する」 |
| Revision | A finished campaign re-rendered in 15s with one changed CTA, reusing the recording | 「構成を直して、この素材のまま作り直す」 |
| Three visual directions | editorial / spotlight / grid produce different frames | `tests/test_core.py::test_each_visual_direction_is_a_different_picture` |
| Landscape film | 1280×720 / H.264 / 24fps, full decode | `verification/artifact-report.json` |
| Portrait film | 720×1280 / H.264 / 24fps, full decode | same |
| Export integrity | ZIP intact, every manifest hash matches, no raw capture, input, logs or private evidence notes | `python examples/verify_artifacts.py` |
| Artifact authorization | Authenticated kit download 200, unauthenticated media 401 | same |
| **Live browser UI** | 14 checks including real video decode and playback, aspect switch, mobile layout at 390px, the exported landing page, pointer-reactive footer; no page errors | `python examples/verify_ui.py --data .launchloom --output checks` |
| Landing page claims | The page shows exactly the approved features from the brief, and no others | same |
| **Landing page deployment** | Five site files written into a configured directory; an unrelated `CNAME` in that directory was left alone; a second preview reported "unchanged" | Set `SITE_DEPLOY_DIR`, then 「書き込む内容を確認」 |
| **Docker** | Image builds; container serves; `doctor` reports `Browser launch: OK`; the bundled sample builds to completion inside the container | `docker compose up -d && docker compose exec studio python -m launchloom demo` |
| Database upgrade | A database written by the previous schema opens and migrates | `tests/test_core.py::test_store_upgrades_an_existing_database` |
| External publication | **None.** No publication records exist in any campaign built here | `verification/artifact-report.json` |

Clip length is the recorded interaction plus the opening and closing card, not
the time it takes to produce a clip. Render speed was measured only on the
machine above. Sample films are silent because no audio was supplied.

## Defects found by running it, and fixed

These were not visible from reading the code or the previous test suite.

1. **`.dockerignore` leaked local state into the image.** `.env`, `.launchloom/`
   (which holds the access token and every campaign) and `.venv/` were all inside
   the build context and copied by `COPY . .`.
2. **Chromium's sandbox could not start in Docker.** Debian's `chromium` package
   does not include the setuid helper — `chromium-sandbox` is a separate package —
   and Docker's default seccomp profile blocks the user-namespace syscalls
   Chromium needs. Both are now handled without disabling either boundary.
3. **`examples/verify_ui.py` could never run in live mode.** It passed page
   predicates as strings, which Playwright evaluates as `eval`, which the
   studio's own `script-src 'self'` correctly forbids. The tool had only ever
   been exercised against an offline snapshot with no CSP.
4. **A schema change could not open an existing database.** A new unique index
   was created in the same script as its table, so on an upgrade it ran before
   the `ALTER TABLE` that adds the column it covers.
5. **The version was declared in three places and they disagreed** (`0.1.0` in
   the package and in every manifest, `0.1.1` in the packaging metadata).
6. **A missing browser produced Playwright's install banner mid-build.** The
   pipeline now fails with the command to run, and `doctor` launches the browser
   instead of checking that a path exists — the headless shell is a separate
   download from the full Chromium build, so a path can exist while nothing runs.
7. **A verification check asserted a fixture, not an invariant.** "The landing
   page has three features" now reads "the landing page shows exactly the
   approved features named in the brief".

Making Launchloom's own launch film, with Launchloom, found two more:

8. **Japanese lines could begin with 、 or 。** Wrapping had no kinsoku shori, so
   any film rendered in Japanese announced that the tool did not know the
   language it was setting. Latin words were also split mid-word — `MP4` became
   `MP` and `4`.
9. **The vertical cut destroyed the interface it was proving.** A 16:10 desktop
   recording was forced into a near-square box, so the product was unreadable at
   9:16. The proof frame now keeps the recording's proportions.

Translating the studio found one more, and it was the worst kind — a feature that
looked present and did nothing:

10. **The review gate showed a blank white frame.** It took literally the first
    frame of the recording, and a screen recording almost always opens on a page
    that has not painted yet. The whole point of the gate is to show what was
    captured, and it was showing nothing. It now samples inside the range the
    operator chose and keeps the first frame with real content.

## Defect found while writing the claims check

`qa.json` reported `only_user_approved_features: true` as a constant. It was an
assertion, not a check — the one promise the tool exists to keep was the one
thing it never verified. It is now computed by reading the export back, it
appears in `qa.json` alongside any findings, and an unsupported claim blocks the
export the way a blank poster does.

## Implemented versus validated against a live service

| Integration | Implemented | Exercised here |
|---|---|---|
| Postiz — integrations, upload, create post | Yes | HTTP contract mocks, validation, approval/hash/state tests. **No live account.** |
| Postiz — `GET /posts` state read, `/posts/{id}/missing` | Yes, against the documented contract | Mocked responses only. **No live account.** |
| Reconciliation of an uncertain send | Yes | Tested through the API with mocked Postiz listings |
| fal | Queue submit, durable ticket, poll, bounded download | Contract mocks. **No paid request was made.** |
| ComfyUI | API workflow, prompt id, history, output download | Contract mocks. **No model was run.** |
| LLM planning | Chat-Completions-compatible, product claims stay canonical | Contract mock. **No external model was called.** |
| Screen recording in the browser | Permission flow, upload, WebM duration normalization | Normalized a real stream-format file. **No macOS/Windows screen-share dialog was driven.** |
| Landing page deployment | Directory target with fingerprinted approval | **Verified on this machine.** Hosted-provider APIs are not implemented. |
| Signed conversions | Per-campaign key, replay window, deduplication | Verified through the API |

## Not verified, or not implemented

- Windows, and Linux desktop, on real hardware. macOS, the Linux container on
  both architectures, and the Linux CI runners were run; no Linux desktop capture
  was exercised.
- The native screen-share permission dialog on any OS.
- Any real social account, any real post, any paid generation.
- Team review and multi-user anything: the authentication here is one operator
  with one token. Reviewing as a team needs accounts, which is P4 work.
- Any language other than Japanese and English.
- Hosted deployment providers, automatic DNS, A/B optimization, text-to-speech or
  music generation, motion blur, callout tracks, more than two audio tracks.
- This is not a penetration test, a license clearance, an audit of whether the
  operator's feature claims are true, or an aesthetic judgement.

A passing suite means the code does what these tests describe on this machine.
It does not mean the film is good, the claims are true, or the launch will work.
