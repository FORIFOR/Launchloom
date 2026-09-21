# Launchloom first proof

Use the bundled synthetic sample before configuring paid generation or live publishing.

## Editable browser walkthrough

Run `python -m launchloom serve`, open `http://127.0.0.1:8787` and enter the local
key printed in that terminal. Select **Edit the sample and make a kit** / **サンプルを編集して作る**.
The bundled Orbit app is recorded. When the storyboard appears, edit one caption,
save it, reload to check the saved copy, then **Save and create films**. Play both
aspect ratios and download the kit. Open its landing page and social drafts too.
The sample is silent without supplied audio; its CTA is disabled without a URL.
The older README GIF shows the automatic demo, before this editable review step.

The standard studio changes film/captions from scene edits; LP/social wording
comes from the brief. All-output scene-copy synchronization belongs to the
experimental creative workflow. See `CREATIVE_WORKFLOWS.md` for that separate path.

If progress stops updating, use **Reconnect and check status**. If the creation
response was lost, the same sample button recovers that request in the same tab.
The URL retains the campaign id. A real worker interruption requires an explicit
retry after checking the cause, not a fresh campaign. The repeatable local test is:

```bash
python tests/first_success_browser_journey.py --output /tmp/launchloom-first-success
```

This drives actual Chrome, SQLite, recording, FFmpeg, download and server restart.
It denies external browser requests and uses explicitly disabled provider settings.
See `quality/verification.md` for the measured revision and limitations, including
the difference between synthetic composition and an actual OS IME session.

## Non-interactive pipeline check

```bash
launchloom doctor
launchloom first-proof --keep ./launchloom-proof
```

`first-proof` is the existing self-test pipeline exposed as the first product-evaluation action. It builds the bundled sample through the real local pipeline and writes evidence that can be inspected or attached to an issue. `--keep` preserves the generated films and launch kit in the directory you choose.

## What to inspect

1. The command exits successfully rather than only starting a server.
2. The kept output contains the generated sample films and launch kit.
3. The self-test report records the checks that actually ran.
4. A failure remains a failure with an actionable error instead of silently enabling a paid or live path.

## Truth boundary

- The bundled input is synthetic. Passing it proves the tested local pipeline completed for that sample; it is not proof of campaign performance or publishing reach.
- Paid video generation remains separately gated.
- Live social publishing remains separately gated and must not be enabled by `first-proof`.
- A generated launch kit is an artifact, not evidence that an external platform accepted or published it.

After the first proof, `launchloom serve` opens the local production board and `launchloom demo` exercises the running studio. Keep provider credentials and any live-publish configuration out of the first-proof path.

## Linux browser verification

The first-success journey defaults to installed Google Chrome. For a Linux image
with system Chromium, select the installed binary explicitly:

```bash
python tests/first_success_browser_journey.py --browser-executable /usr/bin/chromium --output /tmp/launchloom-first-success
```

Chromium's sandbox stays enabled. Use the repository's existing Chromium seccomp
profile and shared-memory allocation in Docker, as in `compose.yaml`; do not
turn the sandbox off to obtain a pass. An image without `git` can receive
`--revision SHA_FROM_HOST` for evidence metadata; the runner independently hashes
the mounted source. Installed `PLAYWRIGHT_BROWSERS_PATH` and `CHROMIUM_EXECUTABLE`
paths are passed into its isolated server, while provider credentials stay excluded.
The process-interruption test is for POSIX (macOS/Linux), not a Windows substitute.
Actual OS IME and human-comparison steps are in
[manual verification](quality/manual-verification.md).
