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
| GET | /artifacts/{id}/{name} | Authenticated allowlisted finished assets |
| GET | /api/integrations | Postiz connected integration list |
| POST | /api/campaigns/{id}/publications | Create immutable draft payload |
| GET | /api/publications/{id}/dry-run | Build Postiz request, no network write |
| POST | /api/publications/{id}/approve | Exact fingerprint + 3 explicit confirmations |
| POST | /api/publications/{id}/submit | Explicit live action when enabled |
| GET | /api/campaigns/{id}/social-analytics | Fetch raw available Postiz analytics |
| POST | /collect | Optional public-token page_view/cta_click event |
| POST | /api/campaigns/{id}/conversions | Authenticated backend-confirmed signup event |

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

For automated production from a brief, use `examples/client.py`. It never posts to
SNS. Use a test-origin allowlist and explicit consent in BuildOptions as required.
Finished campaigns are immutable; revisions create new campaigns. API accepts
operator-approved feature evidence, not independently verified truth.
