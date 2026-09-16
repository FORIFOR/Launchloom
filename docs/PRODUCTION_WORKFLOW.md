# Production workflow / 制作から配信準備まで

## What is connected

One campaign now connects the ordinary studio, scene board, finished-film versions,
and publication review. The standard `create_app()` factory registers all routes;
the CLI is not the only path that works. `/production?campaign=<id>` preserves context.

1. Create a campaign. Choose the recording renderer or **シーン制作・完成動画の取り込み**.
2. Edit scenes. Recording, Seedance, and After Effects are distinct source types.
3. Request Seedance scenes if configured, or export instructions/JSX for external work.
4. Bring back a finished MP4, MOV or WebM. A new normalized MP4 and poster are stored;
   the original is not overwritten and no creative titles or effects are added.
5. Watch the preview and confirm content/rights. Select the version for distribution.
6. Review copy, destination, media and schedule. A no-send preview works without Postiz.
7. Separately release the campaign and approve each submission. A provider receipt
   means **accepted**, not proof the social post was published. Reconcile remote state.

日本語: 完成動画の取り込みだけでは公開されません。配信する版を採用した後も、
公開許可と投稿ごとの承認が必要です。横長・縦長それぞれで採用版を管理します。

## Version and approval contract

Finished films use immutable `finals/<random-id>.mp4` names and SHA-256 checksums.
Selecting another film advances a campaign epoch, supersedes old `draft`/`approved`
publications and resets release permission. A stale browser tab receives HTTP 409.
Selection is blocked while a submission is in flight or its outcome is uncertain.
Already submitted or remotely scheduled posts are **not cancelled** by selection.
Reconcile or cancel those in the provider before arranging a replacement.

Importing a film does not manufacture a landing page; that remains a separate output
of the recording/local-render workflow. Selecting a final does not replace generated
videos inside an existing landing page or ZIP. Those assets keep their provenance.

## Seedance 2.5 scene generation (fal)

Configure on the local server, then restart:

```dotenv
FAL_KEY=your-own-key
ENABLE_PAID_GENERATION=1
GENERATION_BUDGET_USD=your-own-positive-budget
SEEDANCE_END_USER_ID=
```

The dedicated scene adapter uses `bytedance/seedance-2.5/text-to-video` with a saved
scene prompt, 4–30 whole seconds, 480p/720p, 16:9/9:16 and an audio choice. It does not
send the campaign's private evidence or the descriptions of other scenes. Check the
selected prompt itself for private content; this is not a DLP guarantee. Use the
provider's end-user identifier where required by your account and application.

Click **このシーンを生成する**, inspect the exact prompt and settings, enter your current
cost estimate, and confirm transmission and charges. The budget is estimate-based;
it is NOT a hard cap on actual provider billing. Previous provider reservations and
queued estimates count against the configured budget. Use provider-level spending
limits as well. Model rights, acceptable use and actual pricing are the operator's
responsibility; no price is fabricated or silently defaulted.

The same plan/settings/take returns the existing job. A genuinely new creative take
requires a new take number. Failed/interrupted jobs require explicit resume. Stored
fal request tickets are reused; uncertain submissions without a ticket are not blindly
resent. Restarting the studio interrupts queued/running jobs until the operator resumes.
Only not-yet-started jobs can be cancelled locally; the UI does not claim to cancel a
running paid provider request.

A generated scene is **not a finished film**. Review/download it and place it in the
handoff package's `assets/<scene-id>.mp4` before editing in AE. Automatic scene-asset
assembly into an AE project is not implemented in this build.

## Codex / Claude Code and Adobe: explicit local commands

These commands run on the machine where the tools are installed. They do not remotely
control the user's machine from GitHub or GitHub Pages, and are not browser buttons.
API-key authentication is explicit; saved personal CLI login/config is not reused.
External CLI/Adobe live execution has not been verified in the development environment.

After exporting/extracting a production ZIP, request an editable **candidate**:

```sh
# Set CODEX_API_KEY (or ANTHROPIC_API_KEY for --provider claude) in your shell.
python -m launchloom.motion_runner agent \
  --plan production.json --output candidate.jsx \
  --provider codex --confirm-external
```

Use `--model` to choose an available model and `--executable` for an installed native
CLI path. The call uses a temporary configuration home and allowlisted environment;
Postiz/fal/cloud secrets are not passed to the agent. Claude's bare mode, disabled
built-in/MCP tools and Codex's read-only/disabled-shell settings constrain the request.
No tool gets a bypass-permissions flag. Unsupported versions fail rather than falling
back to unrestricted execution. API calls may incur charges; configure provider-side
limits. Timeouts are not proof that no billing occurred.

Only validated JSON output is saved, as a new JSX file. Existing files are not overwritten.
The basic static code check is **not a JavaScript sandbox or a safety guarantee**. Use
a trusted CLI installation, a dedicated OS account/workspace, and read the entire JSX
before giving it Adobe's permissions. Model-authored files are never auto-executed.

On Windows, after reviewing the candidate and saving any current AE work:

```sh
python -m launchloom.motion_runner build \
  --script candidate.jsx --reviewed-sha THE_SHA256_YOU_REVIEWED \
  --executable "C:\\Program Files\\Adobe\\...\\afterfx.exe" --confirm-execution
```

The result means **invoked**, not that AE finished creating a project. Inspect AE.
On macOS, run the reviewed JSX via **File → Scripts → Run Script File**; automatic
macOS JSX invocation is not claimed. The default JSX requires an empty project and
refuses to overwrite an existing `launchloom-project.aep`. Creative prompts are
interpreted by the coding agent, not by the default template itself.

After inspecting/saving the actual AEP, use the installed `aerender` executable:

```sh
python -m launchloom.motion_runner render \
  --project launchloom-project.aep --reviewed-sha THE_AEP_SHA256_YOU_REVIEWED \
  --executable /path/to/aerender --composition Launchloom_Film \
  --output-module "YOUR_INSTALLED_OUTPUT_MODULE" \
  --output finished.mov --confirm-execution
```

Use a real single-file MP4/MOV output module present in your Adobe installation. An
output module is deliberately not guessed. The command checks exit status and probes
the resulting media; it does not prove aesthetic quality. Existing destinations are
refused. Review the result visually, then import it in the production board. AEP/script
hashes do not attest to every linked asset; the final film still needs its own review.

## Verification and release

- Unit/API acceptance uses the **real FastAPI app factory, real SQLite and real FFmpeg
  media**. Only external provider/publisher transports are replaced.
- Scene jobs test consent, privacy of outbound data, de-duplication, budget rejection,
  failures, restart/resume, output retrieval and isolation from publication.
- Motion-runner tests substitute the CLI/Adobe process. They are not real model or
  Adobe verification; one render fixture is actual FFmpeg media for probe validation.
- `python tests/browser_flow.py --output browser-evidence --record` starts the real
  local studio and drives creation, editing, import, selection, navigation and dry-run.
  All external provider flags and keys are disabled. It asserts zero external requests.
- Homepage checks load both pages, play all videos, verify local links, and check 1440px
  and 390px widths. The public workflow video is built from this browser run, not an
  illustrative mock. Its captions explicitly state that no AI/Adobe/social call ran.
- GitHub Actions publishes the matching site only after Python and browser tests pass
  **on main**. Pull-request runs produce review artifacts but never publish the site.
  It copies a fixed allowlist to `gh-pages`, retaining old output videos and kit files.

The development container blocks browser navigation to localhost by administrator
policy. Local API/CLI tests can run there; real navigation tests must run in the
normal CI browser. A test script existing in this repo is not itself a successful run.
Check the latest PR's CI and downloaded reports for results.

### Primary integration references

- https://fal.ai/models/bytedance/seedance-2.5/text-to-video/api
- https://fal.ai/docs/documentation/model-apis/inference/queue
- https://developers.openai.com/codex/non-interactive-mode
- https://github.com/openai/codex/blob/main/codex-rs/core/config.schema.json
- https://code.claude.com/docs/en/cli-reference
- https://helpx.adobe.com/after-effects/using/scripts.html
- https://helpx.adobe.com/after-effects/using/automated-rendering-network-rendering.html

Specifications reviewed September 16, 2026. Live external generation, licensed Adobe
execution, and real social publication still require operator-owned accounts/devices.
