# Security scope / before deploying

This is a **single trusted operator, local-first alpha**, not an audited hosted SaaS.
Do not expose it as an open public API, including behind a shared team password.

## Implemented boundaries

API and artifacts require the local access token. Browser authentication is an
HttpOnly, SameSite=Strict cookie. The initial token is written mode 0600 when
auto-generated. Credentials for fal/LLM/Postiz remain server environment values.
Host allowlisting, cross-origin mutation blocking, CSP, file path checks, media
limits, one-active-job constraints and explicit publication approvals are present.
The origin comparison assumes a correctly configured direct connection/TLS proxy.

URLs for capture require operator-specified origins. The browser has a fresh
context, no inherited cookies, blocked downloads, service workers and WebSocket
connections. Non-GET/HEAD/OPTIONS requests are blocked unless writes to the test
environment are explicitly allowed. Studio API endpoints are not capture targets.
Link-local, metadata, unspecified and multicast destinations are rejected even
when listed. Private-network origins are allowed **only when explicitly configured**
for local staging; this does not make arbitrary private-network browsing safe.

DOM selectors hide passwords, [data-private] and configured elements. This is not
OCR, video/canvas redaction or a guarantee that sensitive information cannot appear.
Always use test accounts/data, inspect the complete recording and final videos,
and review screenshots before publishing. Raw recordings and input files are not
exposed by the artifact route or bundled in the public kit. Evidence notes remain
in the private campaign data; public campaign.json omits them.

FFmpeg is invoked with argument lists, not a shell; file/pipe protocols only.
Uploaded media is bounded by size/dimensions/duration and probed before rendering.
An upload whose browser recorder omitted a WebM duration is remuxed to a bounded,
seekable Matroska file before final validation. Media libraries still need OS
patching and an isolated worker: parsing untrusted media is not risk-free.

The landing-page deploy target is one operator-configured directory. It is
rejected if it overlaps the studio's data directory or the installed package, or
is a home or filesystem root; a destination file name that is a symlink is
refused rather than written through. Only five generated file names are written,
nothing is deleted, and approval is bound to the previewed files' fingerprint.
Deployment still requires the campaign to be released.

Confirmed conversions are signed with a per-campaign key derived from the studio
token, so an operator's backend can report signups without holding studio
credentials, and a leaked campaign key cannot read or change anything. Each
conversion carries the caller's own id under a unique index, and a supplied
timestamp must fall inside a five-minute window. The endpoint counts events; it
is not an identity system and must not receive personal data.

Provider media uses HTTPS, validates public destination addresses and every
redirect. This application-level resolution check is **not a complete defense
against DNS rebinding or all redirect/network attacks**. Use isolated render
workers and an egress proxy/firewall to provide the actual network boundary.

## Known production gaps

No per-user OAuth/IAM, tenant isolation, team roles, secret manager, at-rest database
encryption, distributed queue, execution quotas, global disk cleanup,
content moderation service or penetration-test report. Conversion deduplication is
durable, but within this one local database.
Session expiry is cookie-based, with one long-lived server token, not revocable
per-device sessions. JSON body size has a Content-Length gate; a production proxy
must enforce streamed request limits. Rate limiting is local-memory, not distributed.
Workflows use a single render worker. A long render is not a hosted-SaaS job system.
ComfyUI workflows/custom nodes are operator-trusted and can execute powerful code
on that ComfyUI server; never accept them from untrusted tenants.

Secure cookies must be enabled behind HTTPS. Set explicit public hosts and do not
trust arbitrary forwarded headers. Local filesystem ownership remains part of the
trust boundary. Keep .env, .launchloom, raw captures and keys out of Git and exports.

Chromium sandbox is on by default, and stays on in the supplied container.
Debian's `chromium` package does not ship the setuid sandbox helper, so
`chromium-sandbox` is installed, and Docker's default seccomp profile blocks the
user-namespace syscalls Chromium needs, so `compose.yaml` supplies a
Chromium-aware profile (`docker/chromium-seccomp.json`). Verify with
`docker compose exec studio python -m launchloom doctor`, which launches the
browser rather than checking that a file exists.

`CHROMIUM_NO_SANDBOX=1` and `seccomp=unconfined` are escape hatches for a trusted
process environment, not acceptable multi-user production configurations. Neither
was needed for the verification recorded in `docs/VERIFICATION.md`.

## Publication ambiguity

If a Postiz submission says needs_reconciliation, inspect Postiz and the actual SNS
before taking any further action. The app intentionally has no one-click retry
of an ambiguous live POST. It will list same-account posts with the same opening
text as candidates, but identifying one — or declaring that nothing was created —
is the operator's statement, recorded as such. Creating a new campaign/post can bypass local deduplication,
so an operator must not treat it as a remote-idempotency guarantee.
Do not display access keys, customer data, unapproved feature claims or unlicensed
music in a demo. AI-generated media may require platform-specific disclosures.
