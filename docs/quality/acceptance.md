# Studio first success and local integration acceptance

Frozen before implementation: 2026-09-19, baseline `cb0372631e8128f5517a28e4ae17c4979d14f846`.
The existing `docs/site/ACCEPTANCE.md` covers the public portfolio. This document
covers the running local studio and its HTTP client; it does not replace that record.

## One task

A first-time solo developer starts a private local studio, selects the labelled
Orbit sample, changes one scene caption, saves and reviews it, renders the film,
then downloads a kit containing playable landscape/portrait films, the generated
landing page and social drafts. No service account, paid model or external send
is needed. The sample is an editable demonstration, not footage of their product.

Input: bundled Japanese/English brief and actual bundled-app recording, plus an
operator-edited caption. Output: ZIP, manifest hashes, H.264 videos, SRT, static LP
and social drafts. Success means the edited caption survives save/reload and appears
in the exported storyboard/SRT, both videos decode, and all manifest members match.
Legacy LP/social text comes from the brief, not scene edits; explain this boundary.
The separate experimental v2 editor supports same-revision copy synchronization.

## Fixed checks

All local checks use a fresh temporary database and explicit empty provider keys,
disabled publishing/generation/agents/Adobe, and a localhost server. Browser
requests outside that origin are denied. Record exact OS, CPU, Python, Chrome,
FFmpeg and package versions with the result; no user campaigns or credentials.

| ID | Expected result | Method and evidence |
|---|---|---|
| F1 | Empty studio names the three deliverables, labelled sample, first action and local/no-charge boundary; specialist setup is not required | Running UI, Japanese and English; screenshot and DOM assertions in browser report |
| F2 | Sample stops at `awaiting_review`; edited caption is saved, reload preserves it; explicit render reaches `ready` within 180 seconds on the measured host | Real Chrome + API + SQLite + FFmpeg; record action count/time, campaign states and actual artifact inspection |
| F3 | Downloaded ZIP contains both decodable aspect ratios, LP, drafts, SRT and manifest; hashes match; private input/evidence/token excluded; missing product URL has disabled CTA | Inspect downloaded bytes and full FFmpeg decode; browser plays both films with advancing time and decoded frames; retain ZIP/report |
| R1 | A failed GET is shown as status unknown, not failed/completed; explicit recheck uses GET only, resumes polling, preserves current campaign and editor input | Drop a response in the real browser; compare request methods, URL, input and recovered state |
| R2 | Lost sample/create response can be retried with the same key without a second campaign/job; changed payload with the same key is 409 | Drop response after real commit; concurrent API/store test and database counts, restart/reopen store |
| R3 | A stopped worker becomes `interrupted`; the operator can retry the original local job and reach a valid kit, without changing the campaign id | Real temporary server/worker restart and DB/artifact comparison; no simulation claimed as a process restart |
| C1 | Existing no-key requests and demo default keep their behavior; keyed creation is transactional and rejects conflict; active build options cannot silently differ | Focused API tests, concurrency, old-database migration and existing regression suite |
| C2 | Authenticated OpenAPI describes primary task input/output/status/errors and auth; unauthenticated access denied; client resumes an existing campaign and never automatically repeats writes | Schema assertions and runnable client against local app; explicit timeout/review/retry outcomes, exit codes |
| U1 | At 390px and 200% browser zoom, primary controls and editor are reachable without document horizontal overflow; long Japanese text does not hide actions | Real browser geometry, screenshots; document exact zoom mechanism (CSS scaling alone is not browser zoom) |
| U2 | Keyboard can enter, start, edit, save, render and download; dialogs trap/return focus; async updates do not steal input focus; reduced motion disables animation | Real keyboard and computed-style assertions, report active elements |
| U3 | Japanese composition does not submit or replace input; test composition events and separately a real OS IME session | Browser composition regression + native IME if available; synthetic events alone cannot PASS real OS IME |
| Q1 | Existing tests pass without weakening assertions; Python compile, JS syntax, package build and installed-package smoke pass | Commands, exit codes, logs, built wheel; static typing is NOT_APPLICABLE if no configured typechecker |
| D1 | README/demo/client/API/architecture/roadmap agree with implemented behavior and verification limits | Claims matrix and doc/code review |
| X1 | No native-platform/provider/user-study results fabricated | Real Windows/Linux desktop, licensed AE, paid model, SNS publishing and human comparative usability are BLOCKED absent permission/hardware/participants |

## Comparison protocol

Use the same operator task, supplied material and one caption correction for this
version and a comparable video editor plus static-page/social export workflow.
Measure initial setup requirements, actions to first usable kit, elapsed time,
successful files, recovery from a lost response/restart, and edits retained. Use
the baseline Launchloom revision for a directly reproducible local comparison.
Do not assign aesthetic scores or claim superiority to another product. External
product trials and novice user completion rates are BLOCKED until actually run.

## Decision/evidence rules

Only PASS / FAIL / BLOCKED / NOT_APPLICABLE. Every recorded run includes baseline
revision plus working-tree fingerprint, environment, command, exit code, observed
result and evidence path. A partial check records its untested part explicitly.
Failures stay in the record after correction. At most three improvement rounds:
baseline/contracts; implementation + verification; independent correction/recheck.
Final evidence is indexed in `docs/quality/verification.md`.
