# Creative studio: editable v2 composition and incremental local renders

Open `/production`, select a campaign, then **プレビューで編集 / Preview editor**.
The direct route is `/creative?campaign=<id>`. This is an additive local workflow;
legacy production, provider execution, LP/kit outputs and publication approvals
remain available and are not rewritten by creative saves.

## Working path

1. Select an existing campaign. A completed normal-studio sample reuses its actual
   capture and storyboard. A saved production board preserves its scene plan.
2. Edit copy, duration, source in-point, ordering, brand preset and accent. Caption
   position and size are separate for landscape and portrait. Save explicitly.
3. Confirm rights, then render a single scene or the complete film. Missing footage
   blocks rendering; no paid provider is called to fill a gap. The material picker
   lists only known, hash-checked local recordings or production-board imports.
4. Play the rendered film. The immediate composition view is labelled approximate:
   it is not a real-time renderer or evidence of final typography/motion quality.
5. Adopt the selected complete output after reviewing it. Adoption registers one
   immutable finished-film version and holds local publishing. Repeated adoption
   of the same render/output returns the same registered film. Scene previews
   cannot be adopted as complete films. Publishing needs the existing separate
   release, content/media/account/schedule approval and live-publish configuration.

## What is implemented

- Strict v2 scene/layer contracts, stable original feature indexes, reusable brand
  data inside a campaign, and numeric/finiteness/provenance validation.
- Persisted creative specs with optimistic concurrency and explicit reset when the
  legacy production source changes. Saves do not alter adopted files or posts.
- A deliberately small, offline instruction vocabulary: `5秒にする`, `2秒短く`,
  `文字を上へ`, `文字を下へ`; English: `set to 5`, `shorten by 2`, `text higher`,
  `text lower`. Instructions produce a draft, not an automatic save or provider call.
- Standard 1280×720 / 720×1280 H.264/AAC composition, actual recording audio,
  source in-points, still/gentle-zoom camera, and editorial/spotlight/grid palettes.
- Content-addressed scene rendering. Keys include scene data, selected-aspect
  layout, source hashes, brand data, FPS, renderer version and font bytes.
  Scene reordering rebuilds assembly without recreating scene media. A portrait
  layout edit invalidates that scene's portrait render, not its landscape render.
- Durable queued/running/ready/failed/interrupted jobs, progress and history. One
  creative render at a time across the local studio. Shutdown waits for owned
  render work; startup marks unfinished jobs interrupted, with no blind retry.
- Technical checks for full decoding, duration, dimensions, text safe areas and
  cache/source integrity. Original media is frozen before composition.
- Authenticated, range-capable preview routes and an atomic finished-film/adoption
  registration transaction. Uncertain publication blocks adoption.

## Boundaries, intentionally visible

This is not a general natural-language editor, a new external video-generation
adapter, an AE replacement, or an automatic aesthetic judge. Brand prose is stored
for creative handoff; the standard renderer applies preset/accent but does not
interpret free-form prose. The standard renderer currently supports one video,
up to three text layers and a preset background per scene. Separate image/audio
layers, custom cameras and cursor/action tracking require another renderer and
are rejected rather than silently omitted. Existing mixed audio inside a recording
is preserved. Font coverage remains an operator/environment responsibility.

The editorial specs and old production plans are separate revisions; this release
is not yet a single editable source driving every LP, social draft and renderer.
V2 edits do not automatically regenerate the legacy LP, launch kit or social copy.
The prior `changed_scene_ids()` function is only a local payload diff; use the full
render key for cache reuse. Generated video is never eligible as proof. A recording
and an approved feature link do not independently prove an advertising claim's truth.
Human review still matters.

Per campaign there are at most 30 creative render attempts and the existing 20
finished-film versions. Outputs and caches are local; cleanup is operator-managed.
This is still a single-operator service, not multi-tenant infrastructure. Hashes
are not a tamper-proof ledger against the machine owner.

## API surface

- `GET/PUT /api/campaigns/{cid}/creative-spec`
- `POST /api/campaigns/{cid}/creative-spec/propose-edit`
- `POST /api/campaigns/{cid}/creative-spec/reset`
- `POST/GET /api/campaigns/{cid}/creative-renders`
- `GET /api/campaigns/{cid}/creative-renders/{job_id}`
- `GET /api/campaigns/{cid}/creative-renders/{job_id}/media/{landscape|portrait}`
- `POST /api/campaigns/{cid}/creative-renders/{job_id}/adopt`

All inherit the local session/bearer authentication and cross-origin write guard.
Requests are bounded to 128 KB. Writes and renders bind exact creative/production
revisions; adopting an older composition is rejected. No new publish permissions,
API keys, cloud dependencies, model charges or external-data consent are introduced.

## Verification

`python -m pytest -q tests/test_creative.py tests/test_creative_rendering.py tests/test_creative_api.py`

`python tests/creative_browser_journey.py` drives the real localhost application,
including login, edit/save, FFmpeg rendering, a portrait-only rebuild, adoption and
mobile overflow checks. It uses a labelled typography fixture, not a claimed real
customer campaign. CI retains desktop/mobile screenshots and a result JSON. Neither
this test nor the standard renderer contacts a provider, Adobe or a social account.
