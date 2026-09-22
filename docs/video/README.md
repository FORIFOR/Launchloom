# The demo recording

`homepage/studio-demo.mp4` (1280×720, 23 s) and `homepage/studio-demo-vertical.mp4`
(720×1280, 15 s) are cut from **one real recording of the current studio**, not
from stock or from an earlier build. Both ship with the public site.

## Reproduce it

```bash
python scripts/record-demo.py --output docs/video/raw   # drives the real app in Chrome
python scripts/edit-demo.py  --raw docs/video/raw --output homepage
python scripts/verify-homepage.py                       # 390 / 768 / 1440, real browser
```

`record-demo.py` starts a disposable offline studio with providers, publishing
and paid generation disabled, denies every request outside its own origin, and
**refuses to finish** unless the caption it typed appears in the exported
`captions.srt`. A video that claims an edit reached the film should not be
possible to produce when it did not.

## What is kept, and what is not

- `raw/marks.json` — the timeline the edit script cuts against.
- `edit-report.json` — codec, size, duration and planned-vs-actual length.
- `storyboard.md` — the shot plan, written before the recording.
- `raw/studio-raw.webm` is **gitignored**. It is 5 MB and the scripts above
  regenerate it.

## Honesty constraints held in the edit

- Shortened waits are labelled on screen (`実時間 約47秒を短縮`).
- No audio: the bundled sample has no audio track, so the video is silent.
- The sample is the Orbit app in this repository, not a customer's product.
