# Creative workflows: reviewed AI edits, quality checks and a synchronized kit

These features extend `/creative` without changing legacy production plans,
adopted films, deployed sites or existing publications. All endpoints inherit the
local studio authentication and same-origin write protections.

## Free-form editing

Set `ENABLE_CREATIVE_AI=1`, `LLM_BASE_URL`, `LLM_MODEL` and, when required,
`LLM_API_KEY`. A local loopback Chat-Completions endpoint is supported without a
key. Remote endpoints must use HTTPS. The UI identifies the configured host/model.
`CREATIVE_AI_MAX_TOKENS` defaults to 2400 (256–8000). JSON mode is enabled by default;
set `CREATIVE_AI_JSON_MODE=0` only for a provider that returns JSON without that
parameter. Provider/model compatibility must be verified in the operator's setup.

Open **自由文でAI編集**, describe changes across the film, and explicitly consent to
sending the instruction, on-screen copy, brand notes and approved public feature
text. Private evidence fields, references, file paths, account settings and keys
are excluded. Operator-authored copy/notes can still contain private information.

The model returns bounded operations, not executable code: existing text layers,
durations, hold/gentle-zoom camera, per-aspect caption position/size, complete scene
reordering and preset/accent changes. Scene identity, purpose, claim links, assets,
provenance, provider selection and publishing cannot be changed by these operations.
Unsupported requests are warnings, not invented capabilities. This is free-form
instruction interpretation with a bounded edit vocabulary, not an arbitrary NLE.

A proposal shows before/after changes and warnings. Review the exact copy and its
meaning before **適用して保存** or **適用して再レンダー**. Applying is fingerprint-bound,
revision-bound, expires after one hour and is idempotent. A save in another window,
a changed original production plan or a render in progress blocks stale applies.
AI does not independently prove a rewritten advertising claim is true.

Transport: at most one concurrent creative AI call, 20 attempts/hour including
failed calls, no automatic retry, no redirects or fallback provider, bounded
response bytes and output tokens, and strict local model validation. Tokens and
rate limits are NOT a financial guarantee: configure a monetary cap at the provider.
A timeout can still have incurred charges. Raw provider errors and responses are
not written to logs or exposed in browser error messages. Validated proposal copy
and summaries are stored locally for review.

## Quality and bounded correction

Every new local render receives measured layout checks and up to six midpoint
frame samples per aspect. The report identifies safe-area/line-count problems,
caption overlap with footage and a clearly labelled dense-copy timing heuristic.
Low-variance sampled frames are diagnostics, not aesthetic failures. Real output
file hashes are rechecked before inspecting or exporting them.

**文字配置を自動修正** runs one to three deterministic local passes. It changes only
caption position/size, never wording, media, duration or claims. It stops on no
change and keeps unresolved problems visible. The proposal can be reviewed and
applied with incremental re-rendering. It is not an autonomous aesthetic optimizer.

For optional model-based review, additionally enable `ENABLE_CREATIVE_VISION=1`
and use a vision-capable configured model. After reviewing the complete current
render, consent separately to transmitting up to six sampled still frames plus
scene copy. Frame contents may include private screen data. The model returns
scene-specific observations and typed edits through the same proposal/review gate.
This examines sampled stills, not all motion or audio, and does not assign an
artistic score or predict virality. No model calls are made by local QA or repairs.

## Same-revision launch package

Render every enabled aspect of the complete saved composition. In **動画・LP・SNS原稿を同期**,
review that exact render and its on-screen copy, confirm rights and create a kit.
The kit contains:

- Rendered MP4 formats, poster, scene-headline SRT captions (not speech transcription).
- A responsive static `site/index.html` + CSS, using the same scene text, visual
  preset/accent and CTA as the film; no tracking, external script or font dependency.
- Channel-specific social drafts with UTM links (X/Bluesky length fitting), `copy.json`, and a
  manifest containing the creative revision and SHA-256 for members.

The last CTA scene supplies the CTA text; the hook scene supplies the page hero.
Scene text layers are authoritative, not the editor's cosmetic scene labels.
Channel length fitting may truncate wording, so posts remain review-required drafts.
The product destination/channel selection comes from the original campaign brief.
The package is new and immutable; it does not rewrite the old launch kit or site,
create a live publication, deploy a site, or reuse publication approval. Download
and authenticated page preview routes check integrity. Repeat export of the same
job/brief reuses the existing kit; ten kits/campaign is the limit.

## API

- `GET /api/campaigns/{cid}/creative-workflow`: capabilities, limits, verification boundaries.
- `POST .../creative-spec/ai-proposal`: exact source revisions, instruction, external-data consent.
- `POST .../creative-spec/repair-proposal`: exact source revisions, max_passes (1–3).
- `POST .../creative-proposals/{pid}/apply`: proposal fingerprint, source revisions, content_reviewed.
- `GET .../creative-renders/{jid}/quality/{output}`: measured checks on digest-verified media.
- `POST .../creative-renders/{jid}/visual-review`: revisions, output, data consent, frames_reviewed.
- `POST .../creative-renders/{jid}/kit`: revisions, content_reviewed and rights_confirmed.
- `GET .../creative-kits/{kid}/download`: authenticated immutable ZIP.
- `GET .../creative-kits/{kid}/files/{name}`: allowlisted, hash-checked kit member.

## Verification boundaries

`python -m launchloom.creative_readiness` reports configuration and executable
availability only. It does NOT claim any paid provider, licensed AE instance or
real social account passed a live test. No keys are included. Real external tests
require an operator-owned account, chosen media, approved costs/actions and actual
remote receipts; they cannot be replaced by a mock or a configuration flag.

Tests: `python -m pytest -q tests/test_creative_assistant.py tests/test_creative_workflow.py`.
The transport suite uses HTTP test doubles, including invalid output, refusal/
truncation and no-retry failures. Integration tests use the real authenticated app,
SQLite, FFmpeg, frame extraction, packaging, escaping and revision/hash protections.
`python tests/creative_workflow_browser_journey.py` uses an explicitly labelled model
test double but real UI/API/rendering/ZIP output. It does not contact a paid model.

References checked for implementation (2026-09-19):
- https://developers.openai.com/ja-JP/api/docs/guides/structured-outputs
- https://ffmpeg.org/ffmpeg-filters.html

Remaining limits: real provider/model compatibility, AE execution and real social
publishing are environment-specific and not verified by these test doubles. General
video/audio aesthetic analysis, arbitrary layer insertion and autonomous campaign
optimization are not implemented. The service remains single-operator/local-first.
