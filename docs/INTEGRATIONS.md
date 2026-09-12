# Optional integrations

## Postiz

Run your own Postiz or use an account with its public API. Social-account OAuth
connection, scopes, platform app configuration and credentials are handled in
Postiz, not emulated by this application.

```dotenv
POSTIZ_BASE_URL=https://api.postiz.com/public/v1
POSTIZ_API_KEY=your-own-key
ENABLE_LIVE_PUBLISH=1
```

Self-hosted installations may expose a different public API base path. Configure
the exact documented URL for that installation; do not assume `/api` automatically.
The adapter sends `Authorization: <key>` (not `Bearer <key>`).

Sequence: GET integrations → select a real account → create draft → inspect dry-run
→ review media/content/rights/account → approve fingerprint → submit → store receipt.
For scheduled content the UI converts local time to an explicit ISO-8601 instant;
Postiz does the future dispatch. Launchloom does not need to remain running for a
schedule that Postiz has actually accepted, subject to Postiz operation/retention.

X defaults to `who_can_reply_post: everyone`. Selected generated b-roll adds the
AI disclosure field supported by the adapter. Other disclosure obligations still
need operator review. X length validation is conservative, not a complete official
Unicode/grapheme implementation; the platform remains authoritative.

Additional platform settings are entered as JSON under a post. Check current
Postiz provider docs and connected account capabilities. For example, YouTube
requires title/type; Instagram requires post_type; TikTok requires privacy,
duet/stitch/comment, content and AI settings. The code validates required field
presence, not every evolving Provider enum. Live publishing has not been validated
with a real connected account for every channel in this delivery.

Do not automate replies, DMs or engagement fraud. Outbound batch campaigns need
content review, rate limits, real account authority and the platform's current rules.

## fal

```dotenv
FAL_KEY=your-own-key
FAL_MODEL=operator-selected-owner/model-id
ENABLE_PAID_GENERATION=1
GENERATION_BUDGET_USD=5
```

`FAL_MODEL` above is a placeholder, not an actual model recommendation. Choose a
current video endpoint and copy its **official input schema** into Provider入力.
The UI sends the stored plan's prompt when input.prompt is absent. The response
must contain video.url or videos[0].url. No hardcoded future/preview model is assumed.

Input example shape only (field names depend on your chosen endpoint):

```json
{"prompt":"An original atmospheric product opening, no text or logos"}
```

The worker POSTs to the documented queue, stores request_id/status_url/response_url,
polls status and downloads the completed video. Limit: 200MB/300 seconds/4096px.
The conceptual opening uses the first three seconds; this is not a full-length
cinematic editor. Operator estimate budget is NOT the actual billing cap. Check
provider spending controls. Unknown submission outcomes block automatic resubmission.

## ComfyUI

Set `COMFY_BASE_URL` to your trusted local/server ComfyUI URL. Export an **API format**
workflow from your own ComfyUI with installed, licensed models and nodes. Put it in:

```json
{"workflow":{"YOUR_NODE_ID":{"class_type":"YOUR_INSTALLED_NODE","inputs":{}}}}
```

This is a schema illustration, NOT an executable model workflow. Replace a text
node's text with `{{video_prompt}}` to insert the generated concept prompt. The
adapter POSTs /prompt, stores prompt_id, reads /history/{id}, finds a supported
video output and obtains it with /view. A workflow must save MP4, WebM or MOV video.
No models/custom nodes are bundled, installed or endorsed automatically.

## LLM creative direction

Configure a Chat Completions-compatible base, key and explicit model. The base
usually ends in /v1, where the particular provider requires it. Local compatible
LLMs may omit the key. This is an HTTP compatibility adapter, not a claim that
every model or endpoint supports every requested parameter.

Only operator-supplied product information and approved feature titles/descriptions
are sent. Private evidence notes are not sent by this adapter.
The LLM returns concept, visual_direction and video_prompt. It cannot replace the
canonical feature claims/scenes used in the film/LP/copy. LLM fees are outside the
video estimate ledger, and a retry can issue another LLM request.

## Native recordings

Use the studio's explicit screen-share dialog in a supported desktop browser, or
import an MP4/WebM from Screen Studio / another recorder. No Screen Studio private
API is used. Imported/native video does not carry automatic cursor/action event
metadata in v0.1. Browser-native share permission and recording were not tested
against real macOS/Windows screens in this environment.

Openscreen is a candidate for a future native adapter, not a current dependency.
