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
| store.py | Durable jobs, immutable payload fingerprints, provider tickets, schema migration | Treat in-memory process state as authoritative |
| deploy.py | Copy an approved landing page into one operator-owned directory | Delete, write outside it, or upload anywhere |
| pipeline.py | Orchestration, provenance, packaging, QA | Publish social posts as part of a render |
| server.py | Local authenticated API, upload boundaries, explicit publishing | Claim to be a multi-tenant IAM system |
| web/ | Studio UI, review, permission-based screen capture | Read external API keys |

FilmProvider and Publisher are Python protocols. Providers are explicit adapters;
no generic agent can execute arbitrary shell commands or arbitrary plugins.
No Astra imports, services or credentials are required. Integration should use
HTTP contracts, not link both products' lifecycles.

## Job state

`draft → queued → building → ready`

With `review_plan`, a build stops once the cheap, reversible work is done:

`draft → queued → building → awaiting_review → queued → building → ready`

The gate sits after planning, the landing page and capture, and **before**
rendering and before a video-generation provider is contacted. Opt-in LLM planning
runs before this gate, under its separate data consent. A reviewed storyboard
is stored with `plan_approved`, and the next build uses it verbatim instead of
regenerating one.

Errors: `failed` or `interrupted`. SQLite claims a queued job in a transaction.
A partial unique index prevents two active jobs for one campaign. The worker is
single-process/single-consumer: **do not start Uvicorn with multiple workers**.
A restart marks a running job interrupted; the user reviews and retries with the
original options. Completed recordings and provider tickets can be reused.
Render stages restart rather than checkpointing every frame. There is no hard
render cancellation API in v0.1.

The options comparison handles JSON integer/float equivalence, e.g. 0 == 0.0.

A finished campaign can be **revised**: the storyboard changes and the film is
composed again from the recording and concept clip already on disk. Build options
are compared on every enqueue and cannot change, so a revision can never trigger a
new capture or a second paid generation; the revision counter lands in the
manifest. Changing the brief itself — the claims — still means a new campaign.

Schema changes are applied as `ALTER TABLE` on open, and indexes are created after
that migration: an index declared alongside its table would otherwise run against
a database that does not have the column yet.

Asset roots and hashes make what was reviewed explicit; they are not a tamper-proof
audit ledger against a malicious machine owner.

## Release and publication state

Finishing a film and permitting it to leave the machine are separate decisions.
A campaign carries a `released` flag; `submit` refuses while it is off, and it can
be withdrawn again. Per-channel pacing (a minimum gap, a daily ceiling) is checked
at approval time across every publication of the campaign, so variants cannot
stack up on one account by being created separately.

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

Remote state is **read**, not inferred: `GET /posts?startDate&endDate` is matched
against the stored post ids, and the result (`published`, `queued`, `failed`,
`absent`) is kept in its own columns beside our submission record. For an
uncertain send, same-account look-alikes are offered to the operator as
candidates; only a person decides which, if any, is theirs. Choosing "not
published" returns the record to `approved` so that sending again is an act, not
a retry button.

## Provider state

A paid video request reserves an operator-provided cost estimate before POST.
The returned request ID and status/result URLs are persisted before polling.
A retry resumes an existing ticket. If the POST result was lost, no new request is
sent automatically. Downloads are bounded and installed atomically after validation.
The estimate ledger is lifetime-local-DB, not a Provider billing meter; LLM calls
and all non-video costs are excluded. Enforce monetary caps at the actual Provider.

## Deterministic media

A three-second opening, up to twenty seconds of proof, three-second CTA.
Standard studio: 30fps H.264/yuv420p, faststart, separate 1920×1080 and
1080×1920 layouts. The experimental v2 creative renderer separately uses
1280×720 / 720×1280 at 24fps; do not infer one contract from the other.
Draft = 960×540 and 540×960. Product screen footage is recorded or uploaded;
generated b-roll is only an explicitly labeled conceptual opening.
Cursor coordinates drive clamped eased zoom. Imported footage carries no cursor
metadata; an operator can supply an event track (time, position, action, label)
and it drives the same camera and on-screen labels. Without one, the camera holds
centre. A capture range (start, length) selects which part of the recording
becomes the proof section, and event times shift with the cut.

Three visual directions — editorial, spotlight, grid — change ground, ink,
structure and the fade, not just an accent colour. They are chosen per campaign
and recorded in the manifest.

SRT contains the visual scene headlines, not a transcription; a scene can carry a
caption worded differently from its on-screen headline.

Audio is optional operator-provided licensed material. A music track and a
narration track can be supplied together: each is padded and levelled, music sits
at a fixed level under narration, the mix is loudness-normalised once and cut to
the film's length. No voice cloning, text-to-speech, music generation or
transcription is implemented — these are files the operator already has.

## Metrics

No invented impressions, reach, stars or signups. The optional static-site tracker
sends page_view and cta_click without cookies or visitor identifiers. Counts are
events, not unique people; public client events are forgeable. Confirmed conversions arrive server-to-server on `/conversions`, signed with a key
derived from the studio token for one campaign, so a backend never holds studio
credentials. Each carries the caller's own unique id and is stored under a unique
index, so retries cannot inflate a count; a timestamp, when present, must fall
inside a five-minute window. There is no statistical A/B experiment engine.
The UI gives a limited next-step hint, not a causal growth conclusion.

## Landing page deployment

`deploy.py` writes five generated files into one directory the operator
configured, and does nothing else: no deletion, no path outside that directory, no
upload, no DNS. The target is refused if it overlaps the studio's data directory
or the installed package, if it is a home or filesystem root, or if a destination
name there is a symlink. A preview lists every file, its status against what is
already there, and everything that will be left alone; approval carries that
preview's fingerprint, so a landing page regenerated in the meantime invalidates
it. Hosted provider APIs are deliberately absent — a directory is what a static
host or a repository working copy actually needs, and it is the only target that
can be verified without someone's credentials.

## First-success transport boundary

`Store.create_campaign` owns atomic campaign/initial-job creation and durable
idempotency keys. `Store.enqueue` owns active-job deduplication and immutable build
options. HTTP responses use `contracts.py`; strict input types remain `models.py`.
The browser and `examples/client.py` present those states and explicit actions;
neither implements its own generation, authorization or job store. The client
example is an HTTP adapter, not a stable in-process SDK. Creation replays never
retry jobs or revive publishing approvals. See `COMPATIBILITY.md`.
