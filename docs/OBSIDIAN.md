# Obsidian — studio UI theme

The local studio, the production board and the preview editor use **Obsidian**:
a pure-black ground, hairline borders, a single near-white primary, and quiet
motion. The visual language follows [ObsidianUI](https://www.obsidianui.dev)
(MIT). No ObsidianUI source is vendored: the library is React and Tailwind, and
this studio is plain HTML/CSS/JS, so the design tokens below were read from its
published dark theme and reimplemented as a CSS layer. See `../THIRD_PARTY.md`.

[Quiet Cinema](QUIET_CINEMA.md) remains the system for the public pages
(`homepage/`) and the generated launch-kit landing pages, and its stylesheet
stays in the studio's import chain as the layer Obsidian is applied over.

## Tokens

| Token | Value | Use |
| --- | --- | --- |
| Ground | `#000` | Page, product stage, input fields |
| Surface | `#0a0a0a` | Cards, dialogs, panels |
| Raised | `#141414` | Hover, active nav, clips, pills |
| Border | `#1a1a1a` | Hairline rules between surfaces |
| Border (strong) | `#262626` | Control outlines |
| Foreground | `#fafafa` | Primary text, primary button, focus ring |
| Muted | `#a1a1a1` | Body copy on black |
| Faint | `#8f8f8f` | Labels, eyebrows, footers (the dimmest allowed) |
| Accent | `#fe6e00` | Current pipeline step, one marker per view |
| Positive | `#00bb7f` | Ready state, satisfied checks |
| Radius | 10 / 12 / 16px | Controls / buttons / cards |

Type is Inter Tight with a Japanese fallback, loaded from the operator's OS.
Monospace carries eyebrows, timestamps, IDs and metric figures.

Signature details: the dotted grid on the ground, the lit top edge on the
primary button (`border-top` plus a white-to-transparent gradient), and the
single orange marker that never appears twice in one view.

## How it is applied

The theme is additive, in the order the sheets load:

```
app-base.css → workspace.css → quiet-cinema.css → obsidian.css     (studio)
production.css → obsidian-board.css                                (board)
creative-studio.css → obsidian-board.css                           (preview editor)
```

`app-base.css` is fingerprinted by `tests/test_workspace_styles.py` and
`workspace.css` carries the sizing and hit areas measured for the accessibility
checks, so Obsidian changes colour and surface only. It adds no font, script or
image from the network: the studio must render with the machine offline.

## Boundaries

- **The preview stage is not themed.** `.stage` in the preview editor shows what
  the rendered film will look like, so it is pinned to the renderer's own
  per-preset paper and ink. Repainting it would make the preview disagree with
  the export.
- **The landing-page preview is not themed.** The `iframe` shows the generated
  page as it will be published.
- Reduced motion, `[hidden]`, focus visibility and the 390px reflow behaviour
  are re-asserted by this layer, not weakened.
- The theme is presentation. It does not change publishing, consent, provider or
  capability labelling.

## Verification

`tests/test_obsidian_theme.py` covers the load order, the tokens, the offline
constraint and the pinned preview stage. The measured run is recorded in
[quality/verification.md](quality/verification.md).
