# Studio review simplification — 2026-09-19

User feedback: the running UI was difficult to understand and not intuitive.
The previous automated PASS showed functional completion, not human usability.

Changed the current task screen rather than adding a tutorial overlay:

- Replaced the marketing heading with the concrete task and deliverables.
- Replaced six implementation/distribution stages with three operator steps:
  review content → create films → download the kit. Current step follows saved state.
- Moved Save and the primary **Save and create films** action ahead of the editor.
  The primary action still saves edits and explicitly approves rendering via the
  existing API. It does not publish or send posts.
- Show headlines and captions first, with numbered, plain-language scene roles.
  Supporting text and overall direction remain editable in closed disclosures.
- Show saved/unsaved state as the operator types; preserve the existing save-focus
  and failure/recovery behavior. Identify the recorded still as not a completed film.
- Hide the separate production-workspace link until the standard kit is ready;
  keep advanced reflection boundaries available. Remove decorative sidebar copy.
- Aligned English translations, README walkthroughs and first-proof instructions.
  Updated asset URLs so already-open studios receive the new JS/CSS/translations.

No API, durable store, provider consent or authentication rules changed.

## Executed evidence

Baseline HEAD: `cb0372631e8128f5517a28e4ae17c4979d14f846`, plus uncommitted changes.
Each report carries its own source fingerprint and environment. macOS arm64,
Python 3.14.6, installed Chrome and FFmpeg; fresh offline fixtures.

| Check | Status | Command / evidence |
|---|---|---|
| Full regression, compile, all JS syntax, wheel and installed-wheel smoke | PASS | `.venv/bin/python scripts/verify-local-quality.py --output docs/quality/evidence/ux-checks`, exit 0; [report](evidence/ux-checks/report.json), 841 tests + 13 subtests |
| New review flow and persistent artifacts | PASS | `.venv/bin/python tests/first_success_browser_journey.py --output docs/quality/evidence/ux-final`, exit 0; [report](evidence/ux-final/report.json), first success 42.75s including induced failures |
| Disclosure defaults and save feedback | PASS | Final browser run asserts collapsed concept/direction, visible explicit creation action, dirty state after input, saved state after save, keyboard focus retention |
| Mobile, long input, keyboard, reduced motion, composition regression | PASS | Same real browser journey; [mobile review](evidence/ux-final/review-mobile-long.png) |
| User-visible app | PASS | Existing local UI refreshed only after checking there were no unsaved input values; [review image](evidence/ux-view/review.png) |
| Actual OS IME and fresh 200% zoom on this UI revision | BLOCKED | No new native session for this revision. Prior native zoom evidence applies to the prior layout; synthetic composition/mobile do not replace these checks |
| Novice comparative usability | BLOCKED | No new participant trial; the simpler structure is an implementation response, not a claimed human success rate |

The final browser runner adds disclosure/dirty-state assertions after the full
suite snapshot; application code is identical between those runs. The preceding
`ux-simplified` run also passed. During translation cleanup, the existing orphan-key
test found ten obsolete entries; removed obsolete translations, kept the assertions,
and reran the complete suite successfully.
