# Local API

Base: `http://127.0.0.1:8787`. Server integrations use
`Authorization: Bearer <LAUNCHLOOM_TOKEN>`. Browser sessions use a separate login
request to set the HttpOnly cookie; API keys for third-party services are never
returned by these routes. No automatic cloud API or hosted account is provisioned.

| Method | Path | Operation |
|---|---|---|
| GET | /healthz | Basic health; no secrets |
| POST | /api/session | `{ "token": "..." }` → local session cookie |
| GET | /api/config | Connection flags, not credentials |
| GET/POST | /api/campaigns | List / create strict Brief |
| POST | /api/demo | Create and queue the offline real-app demo |
| GET | /api/campaigns/{id} | State, progress, logs, output URLs, metrics |
| POST | /api/campaigns/{id}/media?kind=capture&rights_confirmed=true | Raw binary body; not multipart. kind can be audio |
| POST | /api/campaigns/{id}/build | Strict BuildOptions. Enqueue once |
| PATCH | /api/campaigns/{id}/plan | Typed storyboard edit while `awaiting_review`, or after `ready` |
| POST | /api/campaigns/{id}/render | Approve the reviewed storyboard and render it |
| POST | /api/campaigns/{id}/revise | Re-render a finished campaign from material it already has |
| GET | /artifacts/{id}/{name} | Authenticated allowlisted finished assets |
| GET | /api/campaigns/{id}/deployment-preview | Exactly what a deploy would write, and what it leaves alone |
| POST | /api/campaigns/{id}/deploy | Write the previewed files into `SITE_DEPLOY_DIR` |
| POST | /api/campaigns/{id}/release | Permit this campaign to leave the machine |
| POST | /api/campaigns/{id}/hold | Withdraw that permission |
| GET | /api/integrations | Postiz connected integration list |
| POST | /api/campaigns/{id}/publications | Create immutable draft payload |
| GET | /api/publications/{id}/dry-run | Build Postiz request, no network write |
| POST | /api/publications/{id}/approve | Exact fingerprint + 3 explicit confirmations + pacing check |
| POST | /api/publications/{id}/submit | Explicit live action, released campaign, live publishing enabled |
| GET | /api/campaigns/{id}/publication-states | What Postiz holds, per submitted post |
| GET | /api/publications/{id}/candidates | Same-account look-alikes for an uncertain send |
| POST | /api/publications/{id}/reconcile | The operator's finding: published (with id) or not published |
| GET | /api/campaigns/{id}/social-analytics | Fetch raw available Postiz analytics |
| GET | /api/campaigns/{id}/conversion-key | Per-campaign signing key for server-to-server conversions |
| POST | /collect | Optional public-token page_view/cta_click event |
| POST | /conversions | Signed, deduplicated backend-confirmed conversion |

Input schemas live in `launchloom/models.py` and reject unknown keys. Examples:

```json
{
  "channel": "x",
  "content": "実際の操作動画と、プロダクトについての原稿。",
  "integration_id": "YOUR_CONNECTED_ACCOUNT_ID",
  "media": "landscape.mp4",
  "schedule_at": "",
  "settings": {"who_can_reply_post": "everyone"}
}
```

After reviewing the actual artifact and target account, approval body:

```json
{
  "fingerprint": "THE_EXACT_64_CHARACTER_FINGERPRINT_RETURNED_BY_THE_DRAFT_API",
  "content_reviewed": true,
  "rights_confirmed": true,
  "account_authorized": true
}
```

The fingerprint above is a placeholder, not a valid token. Approval does not by
itself submit; `/submit` is a separate command. Live publication defaults OFF.

## Reviewing before anything renders

With `"review_plan": true` in BuildOptions, a build stops after capture and the
campaign state becomes `awaiting_review`. Nothing has been rendered and no
provider has been contacted. `PATCH /plan` takes a typed diff:

```json
{
  "concept": "説明の前に、手つきを見せる。",
  "scenes": [
    {"index": 2, "title": "終わったことに、線を引く。", "caption": "消し込みは、気持ちがいい。"}
  ]
}
```

Only wording moves. A scene's `kind` and the approved feature it points at are
structural and are not editable, so an edit cannot attach rewritten text to a
different claim. The stored plan is marked `operator-edited` and is used verbatim
by the next render. `POST /render` approves and renders it.

`POST /revise` takes the same diff shape and re-renders a finished campaign using
the recording and any generated concept clip it already has: no re-capture, no
repeated provider request. Build options cannot change on a revision — changing
what was recorded or requested means a new campaign.

## Reconciling an uncertain submission

A submission that times out becomes `needs_reconciliation` and is never retried
automatically. `GET /candidates` lists what Postiz holds in a window around the
attempt. The operator decides:

```json
{"resolution": "published", "remote_id": "THE_POSTIZ_POST_ID", "note": "確認した場所"}
{"resolution": "not_published", "note": "Postizに該当なし"}
```

`published` records the real post id. `not_published` returns the publication to
`approved`, so sending again is a deliberate act.

## Conversions

`GET /conversion-key` returns a key derived from the studio token for that
campaign only. Your backend signs the raw request body with it:

```
POST /conversions
X-Launchloom-Signature: sha256=HMAC_SHA256(secret, raw_body)
{"campaign_id":"...","conversion_id":"your-own-unique-id","channel":"x","at":"2026-09-12T07:00:00Z"}
```

A repeated `conversion_id` responds 200 with `"duplicate": true` and is counted
once. With `at` present, the timestamp must be within five minutes. Send no
personal data.

---

For automated production from a brief, use `examples/client.py`. It never posts to
SNS. Use a test-origin allowlist and explicit consent in BuildOptions as required.
The API accepts operator-approved feature evidence, not independently verified
truth.
