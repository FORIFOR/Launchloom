# Architecture / contracts

## Boundaries

| Module | Responsibility | Must not do |
|---|---|---|
| models.py | Strict input contracts, consent, features with evidence | Accept arbitrary browser JavaScript |
| planning.py | Canonical scenes, copy drafts, UTM URLs | Invent users, ratings, awards, missing metrics |
| providers.py | Optional LLM, fal, ComfyUI, Postiz HTTP adapters | Silently select paid models, automatically retry uncertain writes |
| capture.py | Explicit browser actions, recordings, cursor-event timeline | Inherit the studio session or a user's browser cookies |
| rendering.py | Decode, camera motion, typography, two independent layouts, encode | Generate counterfeit product screens |
| site.py + templates | Escape supplied text; emit original static LP | Run untrusted generated code |
| store.py | Durable jobs, immutable payload fingerprints, provider tickets | Treat in-memory process state as authoritative |
| pipeline.py | Orchestration, provenance, packaging, QA | Publish social posts as part of a render |
| server.py | Local authenticated API, upload boundaries, explicit publishing | Claim to be a multi-tenant IAM system |
| web/ | Studio UI, review, permission-based screen capture | Read external API keys |

FilmProvider and Publisher are Python protocols. Providers are explicit adapters;
no generic agent can execute arbitrary shell commands or arbitrary plugins.
No Astra imports, services or credentials are required. Integration should use
HTTP contracts, not link both products' lifecycles.

## Job state

`draft → queued → building → ready`

Errors: `failed` or `interrupted`. SQLite claims a queued job in a transaction.
A partial unique index prevents two active jobs for one campaign. The worker is
single-process/single-consumer: **do not start Uvicorn with multiple workers**.
A restart marks a running job interrupted; the user reviews and retries with the
original options. Completed recordings and provider tickets can be reused.
Render stages restart rather than checkpointing every frame. There is no hard
render cancellation API in v0.1.

The options comparison handles JSON integer/float equivalence, e.g. 0 == 0.0.
Changing the brief/options after a ready campaign is deliberately unsupported.
Create a new campaign for a revision. Asset roots and hashes make what was reviewed
explicit; they are not a tamper-proof audit ledger against a malicious machine owner.

## Publication state

`draft → approved → submitting → submitted`

Fingerprint = SHA-256(canonical campaign ID + payload).
Payload includes channel, exact content, media SHA-256, integration ID, scheduled
instant, platform-specific settings, generated-video disclosure and publisher URL.
Approval of one payload does not authorize a different payload. Media hash is
rechecked before approval and submission. A transactional compare-and-set allows
only one local submission attempt per approved publication record.

Postiz POST /upload returns an asset ID/path, then POST /posts receives both.
A response is stored as a receipt. Receipt != confirmed SNS publication. Timeout,
server crash or ambiguous remote outcome => needs_reconciliation, never an automatic
second POST. This is local duplicate prevention, not mathematically exact-once
execution across an external service without an idempotency guarantee.

## Provider state

A paid video request reserves an operator-provided cost estimate before POST.
The returned request ID and status/result URLs are persisted before polling.
A retry resumes an existing ticket. If the POST result was lost, no new request is
sent automatically. Downloads are bounded and installed atomically after validation.
The estimate ledger is lifetime-local-DB, not a Provider billing meter; LLM calls
and all non-video costs are excluded. Enforce monetary caps at the actual Provider.

## Deterministic media

A three-second opening, up to twenty seconds of proof, three-second CTA.
24fps H.264/yuv420p, faststart, separate 1280×720 and 720×1280 layouts.
Draft = 960×540 and 540×960. Product screen footage is recorded or uploaded;
generated b-roll is only an explicitly labeled conceptual opening.
Cursor coordinates drive clamped eased zoom. Imported/native footage has no
cursor metadata in v0.1 and therefore uses a restrained central zoom.

SRT contains the visual scene headlines, not a transcription. Audio is optional
operator-provided licensed material, normalized and mixed separately; no voice
cloning, automatic music generation or transcription is implemented.

## Metrics

No invented impressions, reach, stars or signups. The optional static-site tracker
sends page_view and cta_click without cookies or visitor identifiers. Counts are
events, not unique people; public client events are forgeable. A server-authorized
endpoint accepts backend-confirmed signup events. No unique-conversion IDs or
attribution deduplication exists yet. There is no statistical A/B experiment engine.
The UI gives a limited next-step hint, not a causal growth conclusion.
