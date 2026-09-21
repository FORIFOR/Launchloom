# Local integration and recovery contract

Target: Launchloom package **0.1.1**, with the first-success additions documented
in this working revision. `/healthz` reports the package version, not a guarantee
that two development checkouts are identical. Pin a release or commit and record
the OpenAPI document used by your integration. This is single-operator alpha
software: one SQLite database, one server process/worker, one trusted operator.

## Supported boundary

Use HTTP, not imports of implementation modules. Strict request schemas are
`Brief`, `BuildOptions`, `PlanEdit` in `models.py`; primary responses are
`CampaignRecord`, `CampaignSnapshot`, `BuildJob` in `contracts.py`. Authenticated
`GET /api/openapi.json` exposes OpenAPI 3.1 generated from these actual routes.
Other endpoints are discoverable there, but their untyped response objects are
not a claim of complete SDK-generation support.

`/api/campaigns`, `/api/demo`, campaign status/build/plan/render/revise and
artifact downloads form the local studio integration surface. Existing paths,
no-key behavior and `/api/demo`'s default automatic render are retained. Browser
sample creation opts into `?review_plan=true`; clients can choose that explicitly.
Accept additive response fields, validate required fields, and stop/poll safely
on an unknown state. Requests reject unknown properties. Breaking request/state
changes require release notes and an explicit migration; alpha development is
not a 1.x stability promise. Internal SQLite tables/modules are not a public SDK.
There is no separate supported Python SDK; `examples/client.py` is a runnable
HTTP example. Production execution, v2 creative specs, AI edits and vision routes
remain **experimental**, with their own exact-revision/fingerprint contracts.

## States and operation boundaries

| Campaign state | Meaning | Next action |
|---|---|---|
| `draft` | Brief is stored; no job queued | Upload authorized media, then build |
| `queued` | Durable job accepted | Poll GET; do not start another task |
| `building` | Local worker is executing | Poll GET; closing browser does not cancel |
| `awaiting_review` | Storyboard/capture stored; render awaits approval | PATCH text, inspect saved plan, explicitly POST render |
| `ready` | Package generation completed | Read manifest, inspect/play/download outputs |
| `failed` | Worker recorded an error | Inspect `error` and `events`; explicitly retry original options after fixing cause |
| `interrupted` | Restart recovered an unfinished running job | Review provider status, then explicitly retry original options |

A transport failure is **not** a campaign state. Keep the last snapshot labelled
unconfirmed and GET the same id. Do not infer completion, failure or cancellation.
There is no hard cancellation API; closing a dialog cancels local input only.
Do not issue POST automatically on timeouts. Active build requests with identical
options return the active job; conflicting options are rejected even while busy.

Events are the most recent 80 persisted activity records (`id`, `kind`, `message`,
`created`, in descending id order), not a replayable event stream or webhook.
`stage` and human-readable messages are diagnostic, not enums for business logic.
Progress is approximate work progress, not time remaining. Campaign listing is
limited to the most recent 100; a saved id can still be fetched directly.

## Creating once across a lost response

Generate a random key per creation intent, persist it before sending, then send
`Idempotency-Key` on `POST /api/campaigns` or `POST /api/demo`. Accepted characters:
8–128 ASCII letters, digits, `.`, `_`, `:`, `-`; do not place secrets in keys.
The authenticated operator/database is the scope. Keys survive restarts for the
database lifetime and are shared across both creation routes. Same normalized
brief and initial sample options return the same campaign's **current** state;
the response is not an immutable replay of its original JSON. Reuse with different
input returns 409. Campaign and initial sample job are one SQLite transaction.
Replays do not restart failed jobs or overwrite edits. No-key calls still create
new campaigns. This key does not authorize provider or social retries.

Status 201 means campaign created/resolved. 202 means a local task was accepted;
on replay it may already be complete, waiting for review or failed. Only the
campaign state and verified output establish local success. Postiz acceptance
and confirmed publication remain separate, as documented in `API.md`.

## Errors and permissions

Errors retain the existing JSON envelope: `{"detail": "message"}` for application
errors, or `{"detail": [{"loc": [...], "type": "...", "msg": "...", ...}]}` for
Pydantic validation. Branch on HTTP status and the refreshed resource, not exact
English message text. The API does not currently promise stable per-error codes.

| Status | Response to integration |
|---|---|
| 401 | Authenticate locally again; preserve intent/input |
| 403 | Cross-origin writes forbidden; use trusted same-origin UI or server integration |
| 404 | Missing id or unavailable artifact; never silently select another campaign |
| 409 | Stale state/approval/idempotency conflict; read current state and review |
| 413 / 422 | Correct size/schema/consent/options; retain user input |
| 429 | Rate limited; no automatic write retry |
| 5xx / transport timeout | Outcome uncertain; GET known id or explicitly replay keyed **creation** only |

Every API except login, and every artifact, requires the local bearer token or
HttpOnly, SameSite=Strict session cookie. The token grants the single operator's
full local access; it is not scoped multi-tenant IAM. Use HTTPS off loopback,
disable redirects when attaching credentials, never expose keys in query strings,
and do not forward bearer tokens to URLs returned by an untrusted remote host.
Provider credentials stay on the server. Paid AI, uploads, staging writes, release,
deployment and social publication have separate consent/configuration gates.
The normal studio may call a consented **planning** LLM before the render review;
the local sample does not. A review gate is not a promise that every earlier
operation was offline.

## Runnable client and exit codes

After starting the studio and supplying `LAUNCHLOOM_TOKEN` (or using its local
access-token file):

```bash
python examples/client.py examples/orbit-brief.json --idempotency-key my-first-kit-001
# Keep the printed id. Read/edit the storyboard in /?campaign=THAT_ID.
python examples/client.py --campaign THAT_ID --approve-plan --download ./my-kit.zip
# Observe again without creating or rerendering anything:
python examples/client.py --campaign THAT_ID
# Only after inspecting and fixing a stopped job:
python examples/client.py --campaign THAT_ID --retry-build
```

The default example creates motion graphics, pauses for review, and makes no
external provider call. Supply an options file with `capture_mode: "sample"`
to record the bundled app with the sample brief. The first command prints its
creation key **before** sending and the campaign id immediately on receipt.
Repeat the same brief/key after a lost creation response; never invent a new key
as a retry. `--campaign` never creates a campaign; draft campaigns may start when
explicitly resumed. Changed media/options cannot be applied after a job starts.

Exit 0: ready (and verified download if requested). Exit 2: review required or CLI
argument error (read the message). Exit 3: waiting deadline exceeded; server may
still be working. Exit 1: stopped build/transport/download error. No automatic
write retry or cancellation. Downloads verify ZIP integrity/member SHA-256 and
are installed atomically without replacing an existing destination. These hashes
detect accidental corruption; they are not signatures against the machine owner.

## Artifact/runtime compatibility

Standard studio: HD 1920×1080 / 1080×1920, draft 960×540 / 540×960, 30fps H.264
yuv420p MP4; optional supplied audio. V2 creative renderer: 1280×720 / 720×1280,
24fps H.264/AAC. These are distinct render contracts. SRT is scene captions, not
speech transcription. Legacy scene edits change film/captions; legacy LP and
social text derive from the brief. V2 synchronized packages are explicit actions.
No URL means disabled CTA, not a fake destination. Social files are drafts.

Python >=3.11 is the declared floor; actual tested versions are recorded in
`requirements-tested.txt` and the current verification record. macOS, Windows,
Linux desktop and containers are separate test environments. See
`quality/verification.md` for what this revision actually passed. SQLite upgrade
is additive; back up the whole data directory before an upgrade. Backward
database downgrade is not promised. Static typing is not configured for the
Python/vanilla-JS application; syntax/compilation is not called a typecheck.

References used: [FastAPI OpenAPI generation](https://fastapi.tiangolo.com/how-to/extending-openapi/)
and [W3C resize-text criteria](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html).
Our acceptance checks are not a claim of complete WCAG conformance.
