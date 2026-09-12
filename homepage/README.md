# homepage/

Source of <https://forifor.github.io/Launchloom/> and its Japanese twin at
<https://forifor.github.io/Launchloom/ja/>.

The two pages share the stylesheet but not the media: the Japanese page shows a
recording of the Japanese studio and the Japanese narration, because a page that
says one thing and shows another is the problem this project exists to avoid.
Each carries its own `og.png`, and both are cross-linked with `hreflang`.

One hand-written HTML file with its styles and script inline, plus the assets it
shows. No build step and no dependencies: edit `index.html` and publish.

`launch-kit.zip` is the export for that same campaign, so the page and the
download never drift apart.

`intro.mp4` and `intro-vertical.mp4` are the narrated explainer: the same brief
run through the motion-graphics path with a narration track and a licensed music
bed, cut for both aspect ratios in one pass. They carry audio, so they are not
autoplayed — the page waits for the visitor to press play.

`film.mp4`, `film-vertical.mp4` and their posters are Launchloom's own launch
film — a screen recording of the studio in English, imported back into Launchloom
and cut by the same pipeline the repository installs. Regenerate them by
recording the studio and building a campaign with `capture_mode: upload`.

## Publishing

The `gh-pages` branch holds these files at its root, and GitHub Pages serves it.

```bash
python homepage/publish.py      # copies this folder onto gh-pages and pushes
```

## Checking it before publishing

```bash
python -m http.server 4477 --directory homepage
python homepage/check.py        # real browser: video decodes, no overflow, no errors
```
