# Production board / 制作ボード (beta)

## Scope

A **production handoff**, not an autonomous video-production agent. Existing recording,
FFmpeg rendering and Postiz approval paths remain unchanged. No paid generation or
social posting happens when editing, saving or exporting a production board.

Start with `python -m launchloom serve`. Open the normal studio, enter its local
access token and create a campaign. Then open `/production` on that same server;
the full URL is printed at startup. This is a local application, not a GitHub Pages
hosted editor. `server.create_app()` also registers the production and final-film routes.
The main studio links directly to the selected campaign on the board.

## Working sequence

1. Select a campaign; choose recording, Seedance or After Effects per scene.
2. Edit headings, visual directions, order, duration, aspect ratio and frame rate.
3. Save. Changes are stored separately in `production-plan.json`; concurrent stale
   writes return 409 rather than silently overwriting another browser tab.
4. Export the ZIP. Review its contents before sharing it with an external agent.
5. Follow the README inside. Generate/prepare media in your own environment, ask
   Codex/Claude Code to refine the JSX as needed, and review changes before running.
6. In a blank After Effects project, run the reviewed `build.jsx`. It creates a
   **basic** editable timeline with fades and media. It does not interpret creative
   prompts itself. Missing or too-short footage stops the build; an existing project
   file is not overwritten. Review fonts, layout, sound and rights before rendering.
7. Export H.264/AAC MP4 from your editor. On the production board, import the
   final film, preview it and continue to distribution. Imported versions are immutable;
   a new version needs its own publication fingerprint and approval. Imports hold
   local publishing but do not cancel posts already scheduled at the remote service.

日本語: 同じサーバーの `/production` を開いてください。シーンを編集・保存し、
制作パッケージをダウンロードできます。SeedanceのAPI実行、Codex/Claude Codeの
自動実行、AE遠隔操作、完成動画の自動回収は未実装です。手動取り込みから投稿準備への接続は実装されています。AE用JSXは基本構成の
作成コードであり、実機検証済みの完成テンプレートという意味ではありません。

## Export contract

- `production.json`: versioned, validated public creative plan (1–12 scenes, 120s max).
- `seedance-prompts.md`: manual prompt handoff. No guessed model id/API schema.
- `AGENT_TASK.md`: bounded task for Codex or Claude Code; no automatic execution.
- `build.jsx`: reviewable ExtendScript, with data embedded as escaped JSON literals.
- `assets/README.txt`: fixed `<scene-id>.mp4` filenames; footage is not bundled.
- `README.md`: setup, limitations and human-review steps.

Only approved feature titles seed the plan. Private feature evidence and unapproved
feature titles are not copied. User-authored prompts may still contain private data;
review them before giving the ZIP to external tools. This is not a DLP guarantee.

The production plan and generated script are **not approved publication media**.
Saving a board deliberately leaves existing campaign outputs and approvals unchanged.
New footage must undergo its own review; old approval must not be reused for new media.

## Verification

The added tests cover validation, non-finite durations, duplicate/unsafe ids, private
field exclusion, escaped JSX data, ZIP integrity, persistence, revision conflicts,
size limits and middleware inheritance. External generation, licensed AE execution,
Codex/Claude Code execution and real social posting are not exercised by these tests.

```sh
python -m pytest -q tests/test_production.py tests/test_production_api.py tests/test_production_homepage.py
node --check launchloom/web/production.js
```

Official integration references (checked September 16, 2026):
- https://developers.openai.com/codex/non-interactive-mode
- https://code.claude.com/docs/en/headless
- https://helpx.adobe.com/after-effects/using/scripts.html
- https://helpx.adobe.com/after-effects/using/automated-rendering-network-rendering.html

These references describe future execution integration options; this beta exports
handoff files instead of claiming those integrations have been completed.

Local verification for this change: 28 added tests passed. The full existing repository
regression suite was not run locally. An offline Chromium DOM check, backed by an
isolated FastAPI TestClient, covered edit/save/reorder/delete/export/reload and
390px/1365px layouts. It did not exercise a live studio, existing video playback or
external integrations; live navigation was blocked by the test browser policy.

## Finished films: verified metadata, immutable versions

The normal studio links to the board with the current campaign. The board links back
to distribution with the selected final film. Import a finished H.264 / 8-bit 4:2:0 MP4
with optional AAC audio (200 MB / five minutes maximum; 20 versions per campaign).
Incompatible exports are rejected with export guidance, not silently recompressed.
The server strips container metadata, verifies full decoding and preserves audio.
This is not a content-rights, privacy, aesthetic-quality or AI-detection guarantee.

Each import receives a unique, server-generated filename and SHA-256. The authenticated
artifact route supports video range requests. Imported files are checked against their
registered digest again at preview, draft creation, approval and submission.
The original capture, generated site, kit and local output videos remain unchanged.

Import holds the campaign's local publishing permission. Existing published/scheduled
remote posts are never rewritten or recalled. A publication with an uncertain result
must be reconciled before another film can be imported. New video versions create new
publication fingerprints and require separate review; the AI provenance flag comes
from the import declaration, not from an editable publication request.

API: `GET /api/campaigns/{cid}/final-films`; binary upload to
`POST /api/campaigns/{cid}/final-films/media?rights_confirmed=true&ai_generated=false&title=...`.
Use the existing session or bearer token. Never include API credentials in query strings.

Run the real-app regression tests with `python -m pytest -q tests/test_finished_films.py`.
The actual localhost browser journey is `python tests/browser_journey.py`; it needs
Chromium and uses only bundled fixture content. All external publishing is disabled.
