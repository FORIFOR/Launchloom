# Smart Camera

Launchloom v0.1.1 uses shot-based virtual camera motion instead of click-triggered zoom pulses.

## Rules

1. An interaction creates a camera keyframe.
2. The camera eases into that keyframe with a C2-continuous smootherstep curve.
3. Zoom is held until another meaningful keyframe arrives.
4. Targets within a small dead zone are ignored to avoid micro-jitter.
5. Focus points are clamped into a safe composition area before cropping.
6. No spring, elastic easing, or automatic zoom-out is used.

This is deliberately closer to editorial screen-recording tools: the camera communicates intent rather than following the pointer continuously.

## Imported footage

A recording made outside the studio carries no cursor metadata, so by default the
camera holds centre rather than inventing movement. Supplying an event track gives
imported footage the same treatment as a recorded capture:

```json
[{"time": 1.0, "action": "fill", "x": 0.42, "y": 0.34, "label": "その場で書き留める。"},
 {"time": 2.6, "action": "click", "x": 0.67, "y": 0.34, "label": "一覧の先頭に残る。"}]
```

`time` is measured from the start of the recording, and `x`/`y` are fractions of
the frame. Events must be ordered by time. When a capture range is trimmed, event
times shift with the cut, so a track written against the original recording keeps
working after the start point moves.

The label is what appears on screen for that stretch of the film; it is the
operator's wording, not a transcription and not a generated description.
