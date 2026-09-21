# Contributing

Thanks for looking. This is a small, deliberately honest project, so the bar is
less about code style than about what the code is allowed to claim.

## The one rule

**Claims come from the operator. The tool never invents them.**

A feature appears in a film only because someone typed it into a brief with an
evidence note. Generated video is a labelled conceptual opening, never proof that
something works. Unavailable metrics stay unavailable. If a change would let
Launchloom assert something nobody verified — a feature, a number, a successful
post — it does not belong here, however useful it looks in a demo.

## Getting set up

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m playwright install chromium
python -m launchloom doctor
python -m pytest -q
```

`doctor` launches the browser and resolves the render fonts, rather than checking
that files exist. If it reports a problem, fix that before anything else.

## Before opening a pull request

```bash
python -m pytest -q
python -m compileall -q launchloom
node --check launchloom/web/app.js
```

If you touched the pipeline, the studio or the renderer, also produce something
and look at it:

```bash
python -m launchloom serve          # in one terminal
python -m launchloom demo           # in another
python examples/verify_ui.py --data .launchloom --output checks
python examples/verify_artifacts.py --data .launchloom --output checks
```

Several real defects in this repo were invisible to the test suite and obvious
the moment a film was rendered and watched. Watch the film.

## What is especially welcome

- **[A third language](https://github.com/FORIFOR/Launchloom/issues/3).** The studio renders Japanese and translates it at runtime
  from one table in `launchloom/web/i18n.js`; adding a language means adding a
  table beside `EN`, and nothing else. Three tests guard it: keys must be unique,
  values must not still be Japanese or contain HTML entities, and every key must
  correspond to a string the studio actually produces.
- **[A real Postiz publish on an account you own](https://github.com/FORIFOR/Launchloom/issues/7)**, with the receipt and the
  remote state read back. This is the largest unverified path in the project.
- **Windows ([#5](https://github.com/FORIFOR/Launchloom/issues/5)) and Linux desktop ([#6](https://github.com/FORIFOR/Launchloom/issues/6)) verification**, including fonts and the native
  screen-share permission dialog.
- **[Visual directions](https://github.com/FORIFOR/Launchloom/issues/4).** Three exist (`editorial`, `spotlight`, `grid`) in
  `launchloom/rendering.py`. A fourth should change ground, ink and structure —
  not just an accent colour.
- **Typography for languages that are not Japanese or English.** Line breaking
  currently knows kinsoku shori and Latin word boundaries, and nothing else.

## What will be declined

- Anything that posts, replies, direct-messages, follows or reacts automatically.
- Anything that manufactures engagement, including "growth" automation.
- Metrics that are modelled, estimated or filled in when the real value is
  unavailable.
- Retrying an external write whose outcome is unknown.

## Documentation

For studio/task or integration changes, fix acceptance before implementation using
`docs/quality/acceptance.md`, preserve failing evidence, and run:

```bash
python scripts/verify-local-quality.py --output /tmp/launchloom-quality
python tests/first_success_browser_journey.py --output /tmp/launchloom-first-success
```

The runner records commands, exit codes, package build/import and source hashes.
The browser journey uses a disposable local database, real media and a real worker
restart. Neither establishes external-provider or human-usability success. Do not
label synthetic composition as a native IME test or viewport resizing as browser
zoom. Record PASS / FAIL / BLOCKED / NOT_APPLICABLE for the actual environment.
Public HTTP compatibility and client recovery are described in `docs/COMPATIBILITY.md`.

If behaviour changes, update the doc that describes it, and update
`docs/VERIFICATION.md` if you actually ran something. That file records what was
executed on a real machine; please keep it a record and not a wish list.
