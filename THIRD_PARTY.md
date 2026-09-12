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
| Pillow | Python dependency | HPND and bundled component notices |
| NumPy | Python dependency | BSD-3-Clause and binary component notices |
| FFmpeg / ffprobe | System command; no binaries in this ZIP | Build-dependent LGPL/GPL obligations |
| libx264 | Used when the installed FFmpeg supports it | GPL / applicable commercial terms |
| Postiz | Optional independent HTTP service; source is not copied | AGPL-3.0 for its OSS; hosted service terms separately |
| ComfyUI | Optional independent HTTP service | Project, custom-node, model and output licenses separately |
| fal | Optional hosted model API | Provider and selected model terms; not an OSS dependency |
| System fonts | Loaded from operator OS; no font files shipped | OS/font license |

Screen Studio is a reference for interaction, not a dependency or unofficial API.
Openscreen is an MIT-licensed reference candidate; its code is not integrated or
vendored. Remotion is not a dependency; do not assume its organization/rendering
use is universally free. Inspect actual distribution/build obligations before
shipping a desktop bundle or container image commercially. This is not a license
audit or legal clearance.

Primary sources reviewed for the implementation:
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

## docker/chromium-seccomp.json

Chromium-compatible Docker seccomp profile, taken from the Playwright repository
(`utils/docker/seccomp_profile.json`, microsoft/playwright, Apache-2.0). It keeps
container syscall filtering default-deny while permitting the user-namespace calls
Chromium's own sandbox requires. Without it, Docker's default profile forces the
operator to choose between `CHROMIUM_NO_SANDBOX=1` and `seccomp=unconfined`.
