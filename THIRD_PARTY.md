# Dependencies and references

Original Launchloom code is Apache-2.0. That does **not** relicense dependencies,
model outputs, media, or a separately operated Postiz installation.

| Component | Relationship | License/terms to check |
|---|---|---|
| FastAPI | Python dependency | MIT |
| Pydantic | Python dependency | MIT |
| Uvicorn | Python dependency | BSD-3-Clause |
| HTTPX | Python dependency | BSD-3-Clause |
| Playwright | Python dependency; browser installed separately | Apache-2.0, browser notices separately |
| Pillow | Python dependency | MIT-CMU in Pillow 12.3.0, plus bundled component notices |
| NumPy | Python dependency | BSD-3-Clause and binary component notices |
| FFmpeg / ffprobe | System command; no binaries in this ZIP | Build-dependent LGPL/GPL obligations |
| libx264 | Used when the installed FFmpeg supports it | GPL / applicable commercial terms |
| Postiz | Optional independent HTTP service; source is not copied | AGPL-3.0 for its OSS; hosted service terms separately |
| ComfyUI | Optional independent HTTP service | Project, custom-node, model and output licenses separately |
| fal | Optional hosted model API | Provider and selected model terms; not an OSS dependency |
| System fonts | Loaded from operator OS; no font files shipped | OS/font license |
| ObsidianUI | Design reference for the studio theme; no source vendored | MIT; preserve attribution |

Screen Studio is a reference for interaction, not a dependency or unofficial API.
Openscreen is an MIT-licensed reference candidate; its code is not integrated or
vendored. Remotion is not a dependency; do not assume its organization/rendering
use is universally free. Inspect actual distribution/build obligations before
shipping a desktop bundle or container image commercially. This is not a license
audit or legal clearance.

Primary sources reviewed for the implementation:
- https://www.obsidianui.dev/llms.txt
- https://github.com/getopenscreen/openscreen
- https://github.com/gitroomhq/postiz-app
- https://github.com/gitroomhq/postiz-app/blob/main/LICENSE
- https://docs.postiz.com/public-api/posts/create
- https://docs.postiz.com/public-api/uploads/upload-file
- https://docs.postiz.com/public-api/providers/x
- https://docs.postiz.com/public-api/analytics/post
- https://playwright.dev/docs/videos
- https://ffmpeg.org/legal.html
- https://www.remotion.dev/docs/license
- https://fal.ai/docs/documentation/model-apis/inference/queue
- https://docs.comfy.org/development/comfyui-server/comms_routes

Consult the currently installed releases and their license files, not only this
summary. No implied affiliation with the referenced creators or services.

## Scope of a local application distribution

The Python application wheel contains Launchloom code, web assets, templates and
license notices. It does not contain homepage films, customer recordings, music,
font files, FFmpeg or Chromium executables. A full repository archive is broader:
`homepage/README.md` describes narrated films with a licensed music bed. Do not
assume a license to use music also permits redistributing it in a paid download.
Record the applicable media grant or exclude those materials.

Python dependencies installed separately from their upstream distributions keep
their own licenses. A copied virtual environment or offline wheel collection is
a redistribution of those dependencies. Its inventory must include transitive
packages and binary components, not just the table above. For example, the
2026-10-04 Linux installation contained certifi (MPL-2.0); NumPy's wheel carried
OpenBLAS/LAPACK notices, libgfortran with the GCC Runtime Library Exception, and
libquadmath (LGPL-2.1-or-later). Pillow and Playwright also include component
license files. Preserve and satisfy the licenses of the exact shipped builds.

Generated landing pages include Launchloom template code. Their accompanying
license notices apply to that code; they do not relicense the operator's product
claims, recordings, music, narration, branding or provider outputs. Keep the
notices when distributing the generated site. Encoding a video with FFmpeg does
not, by itself, assign the FFmpeg software license to the video's contents.

See [local distribution and installation](docs/LOCAL_DISTRIBUTION.md) for the
tested package boundary and remaining acceptance checks.

## docker/chromium-seccomp.json

Chromium-compatible Docker seccomp profile, taken from the Playwright repository
(`utils/docker/seccomp_profile.json`, microsoft/playwright, Apache-2.0). It keeps
container syscall filtering default-deny while permitting the user-namespace calls
Chromium's own sandbox requires. Without it, Docker's default profile forces the
operator to choose between `CHROMIUM_NO_SANDBOX=1` and `seccomp=unconfined`.
