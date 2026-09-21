# Remaining verification: executable handoff

These checks require observations that an automated test cannot supply. Record
PASS only after the specified result was observed. Do not enable paid providers,
publishing or remote transmission merely to complete a checklist.

## Actual Japanese IME (macOS / Windows)

Use a temporary offline studio, not the operator's working database. Start the
labelled sample and wait for review. In the first caption field:

1. Activate the installed Japanese input source using the physical keyboard.
2. Type `へんしゅう`, open conversion candidates, choose `編集`, and confirm.
3. Verify that candidate confirmation did not save, render, close the editor, or
   change campaigns. Before explicitly saving, the saved API plan must be unchanged.
4. Press Tab to reach Save and press Enter. Reload. The field and authenticated
   `GET /api/campaigns/{id}` plan must both contain exactly `編集`.
5. Explicitly approve/render. Verify the exported storyboard and SRT contain `編集`.
6. Repeat a conversion then Escape cancellation; save only the intended text.

Retain OS/browser/input-source versions, candidate screenshot if possible, saved
plan and kit; no user account names or unrelated windows. A physical-key observation
may be supplied by the operator, clearly attributed. CDP insertText, DOM composition
events, paste or accessibility setValue do not prove OS candidate conversion.

## Comparative novice task

No invitations or participant data are sent by this repository. A human coordinator
must provide consenting participants and the comparator/version. Use anonymous IDs.
The participant should be new to the tested workflow. Use an offline comparator or
obtain explicit authorization before sending the sample to another service.

Give both workflows the same bundled Orbit brief/recording and this task, without
explaining the implementation: “Create a landscape and portrait product film,
change the first caption to 編集, save it, and deliver both playable films, a static
landing page and social drafts. Recover the same work after the supplied interruption.”

Counterbalance workflow order. Record setup time separately from task time; record
success for each required artifact, explicit actions, help requests, wrong turns,
unsaved edits lost, duplicate work, and recovery outcome. Inspect exported files,
not participant confidence alone. Keep unsupported comparator deliverables visible
as missing; do not silently reduce Launchloom's requirements. Record observations
and participant quotes separately from evaluator interpretation. Small formative
samples reveal problems, not population success rates or superiority.

## Windows / external integrations

Windows requires a Windows runtime and installed FFmpeg/Chrome, then real app
save/reload/render/download and OS IME testing. Linux containers do not substitute
for Windows or native Adobe. The POSIX process-kill branch of the browser runner is
not a Windows test. Record the actual Windows interruption method used.

For each external adapter, specify provider/version, disposable destination,
allowed data, maximum cost, whether submission/publication is permitted, credentials
configured outside evidence, and cleanup/reconciliation owner. Capture remote job
IDs and verify terminal state or actual artifact. An accepted HTTP request is not
completion. Unknown results must be reconciled before a new write. Test doubles and
local previews remain separate from these live results.

Evidence row template:

| Check | Revision + source fingerprint | OS/browser/provider | Actions/command | Exit (or N/A UI) | Observed result | PASS/FAIL/BLOCKED | Evidence |
|---|---|---|---|---|---|---|---|
| Actual IME / human comparison / Windows / named adapter | | | | | | BLOCKED | |
