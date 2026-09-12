# From a working alpha to the full service

Shipped items say what was actually exercised, and on what. Everything else is an
**unimplemented milestone**, not a feature. Do not show future work as product
footage or claim growth outcomes.

## P0 — Real products and real destinations

**Done, and verified on real hardware** (`docs/VERIFICATION.md`):

- The whole pipeline on macOS, not only in a delivery container: capture, render,
  landing page, kit.
- A real staging product recorded over the network — a separate app on its own
  origin, driven by the action DSL, with DOM masking applied.
- Imported footage from outside the studio, with an operator-supplied event track.
- The container: image builds, the bundled sample builds to completion inside it,
  and Chromium's sandbox stays on rather than being switched off to make it work.
- The live browser UI against the running studio, including network, cookies, CSP
  and the exported landing page — the previous record could only snapshot it.
- Six defects that only a real run exposes, listed in the verification record.

**Still open — these need credentials or hardware nobody should fake:**

Publish one approved post to one real connected X account through Postiz, store
the receipt, then read the remote state back and check the published content.
Then LinkedIn and one vertical video channel, including OAuth scopes, privacy,
captions and AI disclosure. Run one paid video endpoint and one operator-owned
ComfyUI workflow with real credentials and models; verify the fees and the
ambiguous-failure path with an actual ambiguous failure. Validate Windows fonts
and the native screen-share permission dialog on macOS and Windows.

Acceptance: zero fake screenshots, duplicate posts or hidden external sends;
all representative paths have a real trace and measured cost, not only mocks.

## P1 — Creative quality and revisions

**Done:**

- Scene review before rendering. A build stops after capture; nothing has been
  rendered and no provider has been contacted.
- Editable scene wording and captions, applied as a typed plan diff — not
  free-form code execution — with scene roles and feature links held structural.
- Three original visual directions that change ground, ink and structure.
- Revision of a finished campaign from material it already has: one scene or CTA
  changes without re-recording or paying for anything else.
- Precise capture ranges (start, length), with imported event times shifted to
  match the cut.
- Cursor-event import for footage recorded outside the studio.

**Still open:** multiple licensed audio tracks and narration/TTS adapters (one
uploaded track is supported today), motion blur, callout and arrow tracks, and
per-scene re-rendering that reuses unchanged scenes instead of composing the film
again.

Acceptance: judge actual text legibility, focus tracking, pacing and end-to-end
intent with humans; not only pixel hashes or a model-assigned score.

## P2 — A managed launch operation

**Done:**

- Explicit campaign release, separate from finishing the film, and withdrawable.
- Remote publication state read from Postiz rather than inferred from acceptance.
- Reconciliation of an uncertain send: candidates are listed, a person decides,
  and "not published" returns the record to approved instead of offering a blind
  retry.
- Per-channel pacing limits so scheduled variants cannot stack up on one account.
- Landing-page deployment into a directory the operator owns, behind a preview
  approved by fingerprint.
- A guided connection panel for Postiz, including which channels need extra
  platform settings.
- Signed server-to-server conversions with the caller's own unique ids and
  durable deduplication.

**Still open:** hosted-provider deployment (Netlify, Cloudflare Pages and the
like), artifact reuse across campaigns, and team review — which needs real
accounts and therefore belongs with P4, not before it. A single access token
cannot represent two reviewers, and pretending otherwise would be worse than not
having the feature.

Acceptance: one approved campaign can run its agreed sequence without daily
manual copy/paste, yet no account/permission/content scope is expanded implicitly.

## P3 — A/B learning that can be trusted

Not started. Render two controlled hook variants, predeclare one conversion
objective and a minimum observation window, collect sufficient real traffic,
compare a single variable, report uncertainty. Avoid declaring a winner from 12
impressions. Organic SNS performance is confounded; distinguish observational
advice from randomized-site tests and causal evidence. Do not promise virality or
GitHub stars.

The pieces that make this possible — deduplicated conversions, scheduled
variants, pacing — exist. The statistics do not.

## P4 — Multi-tenant paid service

Not started. Isolated browser/media workers, durable distributed queue, object
storage, OAuth/IAM and team roles, KMS-backed secrets, usage billing, budget
limits, retention/deletion, audit trails, rate limits and legal/abuse review.
Keep the local OSS core useful and provider-independent. Sell managed execution,
team operations and brand continuity, not an artificially broken local renderer.

Astra can become an optional client/plugin. Launchloom must not require Astra or
its database, identity service, GUI, model provider or installation lifecycle.
