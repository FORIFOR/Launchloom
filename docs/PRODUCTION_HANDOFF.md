# Production board / 制作ボード (beta)

## Scope

The production board now has two layers: a safe **handoff/export** path and an
explicitly enabled **execution** path. Saving or exporting a board still makes no
network request. Seedance, coding agents and Adobe each require a separate operator
action and their own settings; none of them can silently trigger social publishing.

Start with `python -m launchloom serve`, open `/production`, and select the campaign.
The normal studio and the production board preserve the selected campaign between them.

## Execution sequence

1. Edit and save the scene plan. Every execution request is bound to the exact
   SHA-256 production revision; a changed plan returns a conflict instead of running
   stale instructions.
2. Prepare the isolated production workspace. It contains only the reviewed plan,
   agent task, JSX and scene assets. Parent folders, `.env` and account data are not
   copied into it.
3. For recording scenes, import an H.264/AAC MP4/MOV after confirming usage rights.
   The server strips metadata, fully decodes the file and records its SHA-256.
4. For a Seedance scene, either import your own clip or explicitly call fal's
   `bytedance/seedance-2.5/text-to-video` endpoint. Launchloom supports 480p/720p,
   4–30 second explicit duration and 16:9/9:16 from the production plan. The UI shows
   the current configured estimate and asks for confirmation immediately before the
   paid request. Provider request IDs are stored so a timeout is resumed/reconciled
   instead of blindly submitting another charge.
5. Optionally run Codex or Claude Code to refine only `build.jsx`. Codex uses
   `codex exec --sandbox workspace-write --ignore-user-config --ignore-rules
   --skip-git-repo-check`; Claude uses bare print mode with only Read/Edit pre-approved.
   The resulting JSX is rejected if it removes required scene/project identifiers or
   contains obvious network, shell or credential access. Agent output text is not
   returned through the browser API, avoiding accidental secret/log exposure.
6. After Effects remains split into project creation and rendering. Adobe documents
   command-line JSX execution using `afterfx.exe -r` on Windows, so Launchloom only
   automates that step on Windows. On macOS, open the reviewed `build.jsx` from
   **File > Scripts > Run Script File**. The script creates `launchloom-project.aep`,
   the editable composition and a render-queue output at `render/ae-master.mov`.
7. With `AERENDER_EXECUTABLE` configured, Launchloom can run `aerender` on the reviewed
   AEP on Windows or macOS. The master is transcoded to H.264/AAC and registered as a
   new immutable finished-film version. This resets local release permission; it does
   **not** publish or cancel anything remotely.
8. Preview the finished film, create a post draft, review its fingerprint and approve
   it separately. Live Postiz submission still additionally requires
   `ENABLE_LIVE_PUBLISH=1` and campaign release. API acceptance remains distinct from
   confirmed publication, and reconciliation is preserved.

日本語: 保存・ZIP出力だけでは外部通信しません。Seedance 2.5、有料生成、Codex /
Claude Code、After Effects、SNS公開はそれぞれ独立した明示操作です。AEのJSX自動実行は
Adobeが公式に案内しているWindowsの`afterfx.exe -r`だけを自動化し、macOSではJSXを
AEから手動実行します。`aerender`はAEP作成後に両OSで利用できます。生成・レンダーした
動画は新しい完成版として取り込み、以前の公開許可を再利用しません。

## Configuration

Seedance uses the existing paid-generation guard plus a dedicated fixed model ID:

```env
FAL_KEY=...
ENABLE_PAID_GENERATION=1
GENERATION_BUDGET_USD=20
SEEDANCE_PRICE_PER_1K_TOKENS_USD=0.0214
```

The price value is an operator-maintained estimate, not a billing authority. As of
2026-09-17, fal documents token billing as
`output_height * output_width * duration * 24 / 1024`, at $0.0214/1000 tokens.
Review the provider page before changing the configured price.

Local agents are disabled by default:

```env
ENABLE_LOCAL_AGENTS=1
CODEX_API_KEY=...       # when using Codex
ANTHROPIC_API_KEY=...   # when using Claude Code
```

Adobe execution is also disabled by default:

```env
ENABLE_AFTER_EFFECTS=1
AFTERFX_EXECUTABLE=...   # Windows project-build step only
AERENDER_EXECUTABLE=...  # Windows or macOS render step
```

## Export contract

The ZIP is still useful when execution is unavailable. It contains `production.json`,
`seedance-prompts.md`, `AGENT_TASK.md`, `build.jsx`, `assets/README.txt` and a README.
Exporting it never starts a provider, agent, Adobe process or publisher. Only approved
feature titles seed the plan; private evidence is excluded. User-authored scene prompts
can still contain private data, so external-data review remains the operator's job.

## Verification boundary

The repository tests exercise validation, revision binding, workspace isolation, cost
estimates, explicit-confirmation gates, asset integrity, agent command construction,
Adobe command construction, finished-film registration and the existing browser journey.
They use fakes/local fixtures for external executables and do **not** spend money, call a
real Seedance account, run a licensed After Effects installation, use real Codex/Claude
credentials, or publish to a real social account. Those integrations are therefore
implemented but live-provider / visual-quality verification remains environment-specific.

Official references checked 2026-09-17:
- https://fal.ai/models/bytedance/seedance-2.5/text-to-video/api
- https://learn.chatgpt.com/docs/non-interactive-mode
- https://code.claude.com/docs/en/headless
- https://helpx.adobe.com/after-effects/desktop/automate-in-after-effects/automate-animation/scripts.html
- https://helpx.adobe.com/after-effects/desktop/render-and-export/automate-rendering/automated-rendering-network-rendering.html

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
