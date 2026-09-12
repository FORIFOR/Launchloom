# Testing this

Everything below has only ever been run by one person, on one Mac, plus a Linux
container and a CI runner. That is the honest limit of what
[docs/VERIFICATION.md](docs/VERIFICATION.md) can claim, and the fastest way to
move it is someone else's machine.

## The two-minute version

```bash
git clone https://github.com/FORIFOR/Launchloom.git && cd Launchloom
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e . && python -m playwright install chromium
python -m launchloom selftest
```

`selftest` runs the real pipeline — it drives the bundled app in a browser,
records it, renders both cuts, writes a landing page and a kit, then checks what
came out. It works in a temporary directory, touches nothing else, and needs no
account, no API key and no network.

It takes about twenty seconds and writes `launchloom-selftest.txt`. That file is
the report: paste it into
[a tester report](https://github.com/FORIFOR/Launchloom/issues/new?template=tester-report.yml)
and you are done.

Add `--keep ./out` if you want the films and the kit left somewhere you can open
them. **Please do open them.** The automated checks can tell you a file decodes;
only a person can tell you it looks wrong.

## Without installing anything

If Docker is easier than a Python environment:

```bash
docker run --rm -e CHROMIUM_NO_SANDBOX=1 ghcr.io/forifor/launchloom \
  python -m launchloom selftest
```

The image carries both `linux/amd64` and `linux/arm64`, so this runs on an Intel
box and on an Apple Silicon Mac alike — both were pulled and run before this was
written. About twenty seconds, then copy the report out of the terminal.

Two honest caveats. `CHROMIUM_NO_SANDBOX=1` turns off Chromium's own sandbox,
which is acceptable here because the selftest only ever loads HTML the image
already contains, in a container you are about to throw away — for recording
anything of your own, use `docker compose up`, which keeps both the container's
seccomp filter and Chromium's sandbox. And a container is Linux: it tells me
nothing about whether Launchloom works on **your** operating system, which is the
thing I most need to know.

## What would help most, in order

1. **[Windows](https://github.com/FORIFOR/Launchloom/issues/5).** Never run. Fonts, FFmpeg on PATH, the Playwright
   browser, and whether the film comes out with readable Japanese and Latin text.
2. **[A Linux desktop](https://github.com/FORIFOR/Launchloom/issues/6).** The container works on both
   architectures; a desktop session with real fonts and a real screen-share
   permission dialog has not been tried.
3. **[A real publish through Postiz](https://github.com/FORIFOR/Launchloom/issues/7)**, on an account you own. The integration is
   implemented and contract-tested, but no live social account has ever been
   used. The receipt, and the remote state read back afterwards, are what I have
   never seen. Live publishing is off by default and every post needs an explicit
   approval, so nothing can go out by accident.
4. **Your own product, not the sample.** Record a staging URL you control, or
   import a screen recording you already have. Whether the camera work and the
   copy make sense for something that is not Orbit is genuinely unknown.
5. **A paid generation endpoint.** fal and ComfyUI are contract-tested only. If
   you run one, the thing I want to know is what happens when it fails halfway.

## What you should not do

- Do not point capture at a production environment, or at anything holding real
  customer data. Use a staging environment with test data. The browser gets a
  fresh context and inherits no cookies, but DOM masking is not a guarantee.
- Do not expose the studio to the internet. The authentication is one token for
  one operator.

## If it breaks

That is the more useful outcome, and it is what the report is for. Paste
whatever the terminal printed. `python -m launchloom doctor` on its own is also
useful — it launches the browser and resolves the render fonts rather than
checking that files exist, which is how several environment problems have turned
out to be visible before a build ever starts.

## If you would rather write code

Two issues are scoped so that nothing else has to be understood first:

- [Add a third language to the studio](https://github.com/FORIFOR/Launchloom/issues/3) — one table in one file,
  with three tests already guarding it.
- [A fourth visual direction for the film](https://github.com/FORIFOR/Launchloom/issues/4) — ground, ink and
  structure, not an accent colour.
