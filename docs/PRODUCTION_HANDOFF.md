# Production board / 制作ボード (beta)

## Scope

A **production handoff**, not an autonomous video-production agent. Existing recording,
FFmpeg rendering and Postiz approval paths remain unchanged. No paid generation or
social posting happens when editing, saving or exporting a production board.

Start with `python -m launchloom serve`. Open the normal studio, enter its local
access token and create a campaign. Then open `/production` on that same server;
the full URL is printed at startup. This is a local application, not a GitHub Pages
hosted editor. Code that constructs `server.create_app()` directly should explicitly
call `production_api.register_production_routes(app)` as the CLI does.

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
7. Rendering, returning the completed film and attaching it to a publication remain
   manual. No imported final-film publishing bridge is implemented in this beta.

日本語: 同じサーバーの `/production` を開いてください。シーンを編集・保存し、
制作パッケージをダウンロードできます。SeedanceのAPI実行、Codex/Claude Codeの
自動実行、AE遠隔操作、完成動画の自動取り込みは未実装です。AE用JSXは基本構成の
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
