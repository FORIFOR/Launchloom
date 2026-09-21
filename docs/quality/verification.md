# Local OSS quality verification — 2026-09-19

**Evidence location:** the run outputs linked below (`evidence/`) are retained on
the machine that produced them and are not committed; `.gitignore` excludes the
tree. The links therefore resolve only in a checkout that still holds those runs.
Request the artefacts, or re-run the recorded commands, before relying on a link.

Latest UI revision: [review-screen simplification](ux-improvement.md), with a fresh
841-test/package run and real browser artifact/recovery verification. Earlier
source fingerprints below describe earlier revisions, not this new layout.

## Studio theme: Obsidian

The studio, production board and preview editor were re-themed after
[ObsidianUI](https://www.obsidianui.dev); see [OBSIDIAN.md](../OBSIDIAN.md). The
change is a colour and surface layer over the existing stylesheets, so the sizing
and hit areas measured for the accessibility checks are unchanged.

Measured on macOS with installed Chrome and FFmpeg: the full suite passed at 848
tests, and `tests/first_success_browser_journey.py` passed F1, F2, F3, R1, R2,
R3, U2, U3-composition, C2 and network, with zero page errors and zero external
requests. Document width equalled viewport width at 390px, and animations stayed
disabled under reduced motion. **U3-native-IME and U1-zoom remain BLOCKED** for
the same reasons recorded below; the theme did not change their status.

Two surfaces are deliberately not themed, because each is a preview of real
output: the preview editor's stage keeps the renderer's own per-preset colours,
and the landing-page frame shows the generated page as it will be published.

## Follow-up: resolve unmet checks

The request to resolve all remaining items produced an additional **Linux PASS**:
actual Chromium recording, editable review/save/reload, response-loss recovery,
both decoded films and hash-verified kit, explicit SDK resume, keyboard/reduced
motion, and actual worker process restart all passed inside the existing local
Linux aarch64 image. The complete browser run exited 0, with first success in
55.75 seconds. Docker networking was disabled, no port was published, and
Chromium's sandbox remained enabled with the repository's existing seccomp profile.
The macOS browser run was also repeated with sandbox explicitly enabled, exit 0.

The test runner now accepts an installed Chromium binary and an explicitly supplied
host revision for images without git. It preserves installed Playwright runtime
paths in its isolated server environment, without passing provider credentials.
The source is always fingerprinted. Product code is unchanged from the full
841-test run; this follow-up changes the portable verification harness and docs.

[Follow-up evidence](evidence/followup/report.json) retains initial failures and
exact commands/environments. [Linux actual kit](evidence/followup/linux-browser-3/launch-kit.zip)
and [Linux browser report](evidence/followup/linux-browser-3/report.json) are inspectable.
This proves a Linux container workflow, not Windows or native Adobe execution.

**Still BLOCKED:** actual Japanese OS IME candidate conversion (installed input
sources confirmed, automation still produces literal Latin text; physical operator
input requested), Windows/Adobe runtime, live external actions under the original
prohibition, and comparative human usability without participants. A local IME
test tab is retained for operator input. [Manual verification](manual-verification.md)
defines the exact pending actions and required evidence. None of these remaining
checks was relabelled PASS or waived. The historical report below retains its
original run boundaries.

**Selected local workflow: PASS. Full acceptance: BLOCKED** on actual OS Japanese
IME and unperformed human/platform/provider evaluation. This is evidence for a
working local task, not a claim of parity or superiority to commercial products.

Baseline revision: `cb0372631e8128f5517a28e4ae17c4979d14f846`.
Implementation remains an uncommitted working-tree change; each execution report
records its own source SHA-256 and `source-files.json` where provided. Earlier
reports are not evidence for later changes. The final automated source is recorded
in [checks-final-focus/report.json](evidence/checks-final-focus/report.json) and
[round-3b/report.json](evidence/round-3b/report.json). Documentation-only changes
following these runs do not change executable sources.

## Outcome and boundaries

A fresh local user can select the labelled Orbit sample, edit/save a caption,
reload, explicitly render, play landscape and portrait films, then download a ZIP
with a landing page, three social drafts, SRT and a hash manifest. The measured
browser run took **42.49 seconds**, including intentional failures and recovery,
on this host; this is not a measured novice-user completion time. The normal path
has three explicit product actions after login: start sample, save edits, approve
render; the user then chooses playback and download. Keyboard traversal and
induced recovery actions are additional, not hidden inside this action count.

Local creation keys are durable and transactional. A lost committed response or
lost follow-up GET recovers the same sample instead of creating another one.
GET outages retain unsaved input and say the result is unconfirmed. Actual worker
termination leads to `interrupted` and explicit retry of the same campaign.
Core rules remain in Store/pipeline; UI and the example HTTP client use that API.
The primary creation/status/build/plan/render routes have generated OpenAPI input,
response and error contracts. This is alpha, single-operator local software;
experimental integrations and the absence of a separately supported SDK are explicit.

See [acceptance](acceptance.md), [claim audit](claims.md), and
[compatibility](../COMPATIBILITY.md). README, both languages, current demo guide,
API, client example, architecture and roadmap were aligned. Standard film output
is 1920×1080 / 1080×1920 at 30fps; standard scene edits do not rewrite LP/social copy.
Optional planning LLM work can precede render review; the tested sample is offline.

## Environment and final commands

macOS 26.6.2 arm64; Python 3.14.6; Chrome 153.0.8010.48; FFmpeg 9.0.1;
FastAPI 0.128.8, Pydantic 2.13.5, Playwright 1.57.0, pytest 9.1.1.
Tests use temporary databases, explicit disabled provider/publishing settings and
loopback. Automated browser contexts deny all requests outside their own origin.
No user data directory is used. Servers created for these checks are stopped.

| Command | Exit | Evidence / result |
|---|---:|---|
| `.venv/bin/python scripts/verify-local-quality.py --output docs/quality/evidence/checks-final-focus` | 0 | [Report](evidence/checks-final-focus/report.json): Python compile, all JS syntax checks, full pytest, offline wheel build, isolated installed-wheel smoke |
| `.venv/bin/python tests/first_success_browser_journey.py --output docs/quality/evidence/round-3b` | 0 | [Report](evidence/round-3b/report.json): live browser, persistence, real films, ZIP and worker restart |
| `.venv/bin/python docs/quality/evidence/independent/verify.py` | 0 | [Independent report](evidence/independent/README.md): separate verifier, temp DB and Chrome; SDK/unsaved-input/artifact verification |
| Native Chrome menu/zoom/edit/save/reload through CUA | N/A | [Native record](evidence/native-verification.json); UI actions do not have a shell exit code; authenticated saved-plan check exited 0 |

The full suite result is **841 passed, 13 subtests passed**. One upstream Starlette
AnyIO deprecation warning remains. No configured static typechecker exists;
compile/schema/runtime checks are recorded separately, not relabelled typechecking.
Individual commands, exit codes, package versions, logs and the wheel are retained
inside the checks directory. No network package install was needed (`--no-index`).

## Acceptance decisions

| ID | Decision | Observed result and evidence |
|---|---|---|
| F1 | PASS | JP mobile and EN desktop empty screens name deliverables, first action, labelled sample and local/no-charge boundary; [screenshots/report](evidence/round-3b/report.json) |
| F2 | PASS | Awaiting-review → edited saved/reloaded caption → explicit render → ready in 42.49s; browser and independent SDK records |
| F3 | PASS | [Actual ZIP](evidence/round-3b/launch-kit.zip): 16 members, all manifest hashes match, edited SRT, three drafts, private files excluded; both MP4s fully decoded with FFmpeg exit 0 and Chrome advancing frames; LP playback confirmed |
| R1 | PASS | Aborted GET shows unconfirmed connection banner; explicit GET-only recheck preserves campaign URL and unsaved caption |
| R2 | PASS | Lost committed POST, reload, then lost follow-up GET: one campaign/job; tests cover concurrent replay, reopened database, rollback and 409 conflict |
| R3 | PASS | Real process-group kill during FFmpeg, actual restart, interrupted state, explicit same-id retry to ready; browser report |
| C1 | PASS | Existing no-key/default demo behavior retained; additive database migration, transactional key/job and conflicting active options tested; full regressions pass |
| C2 | PASS | Authenticated OpenAPI covers primary input/output/error/auth contracts, including PATCH plan/POST render added after independent review; client resumes review (exit 2) and ready/download (exit 0), never automatically retries writes |
| U1 | PASS | 390px and long Japanese input: automated document overflow assertions; real native 200%: controls reachable, save/reload preserved caption, visual observation and HTTP saved-plan match. Native test is separate from viewport emulation |
| U2 | PASS | Keyboard login/start/edit/save/render/download, dialog focus containment/return, save-focus retention and reduced-motion styles; final browser assertions |
| U3 synthetic composition | PASS | Chrome composition/commit retained Japanese text and did not submit; this is only a regression test |
| U3 actual OS IME | BLOCKED | Native shortcut/physical-key attempt did not activate Japanese conversion; candidate selection and confirmation were not validated. No synthetic test substituted |
| Q1 compile/syntax/test/package | PASS | Full suite, offline wheel and isolated installed-package smoke, exact command/exit logs |
| Q1 static typecheck | NOT_APPLICABLE | No configured static typechecker in this project |
| D1 | PASS | [Claim audit](claims.md) and aligned entry/API/client/compatibility docs distinguish executed local features, implemented adapters/test doubles and unverified live claims |
| X1 providers/native platforms | BLOCKED | No permission for external data transmission, generation spending, social publication or deployment; licensed Adobe and other OS execution not available in this run |
| Comparative human usability | BLOCKED | No novice participants or comparable commercial-product trial. No AI aesthetic score or success-rate claim |
| Native app testing | NOT_APPLICABLE | Selected product task is a web studio; native Adobe integration remains separately BLOCKED |

## Three improvement rounds and failures retained

1. **Baseline and contracts:** inspected README, implementation, tests and launch
   path; selected one task and fixed measurable [acceptance](acceptance.md) before
   implementation. Preserved existing architecture and user changes (initial tree clean).
2. **Implementation and execution:** beginner review path, durable creation,
   reconnection, resumable HTTP example, schema and documentation changes. Browser
   attempts [round-2](evidence/round-2/report.json) and
   [round-2b](evidence/round-2b/report.json) failed due to test-harness CSP-expression
   and ambiguous-caption-selector errors; corrected the harness without weakening
   CSP or assertions. [round-2c](evidence/round-2c/report.json) passed.
   [checks-round-2](evidence/checks-round-2/report.json) found an orphan translation
   after a log-text correction; fixed the translation and retained the failure.
3. **Independent review and correction:** a separate implementation-independent
   agent validated saved input, SDK recovery and artifacts; its original selector
   failure is retained under `independent/attempt-1`. Added missing plan/render
   OpenAPI responses, retained creation intent through follow-up read failure,
   bounded stalled GETs, and pinned in-flight save/approve to its original campaign.
   [round-3](evidence/round-3/report.json) found save-button focus loss; fixed it and
   reran the same assertion successfully in `round-3b`. Final checks include the fix.

The four requested custom Skills were searched for but not installed; none was
used or reported as used. Independent verification ran in a separate agent
session. All changes and evidence are local; no push, merge, publication,
deployment, paid generation or third-party content submission was performed.
