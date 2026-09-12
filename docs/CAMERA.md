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
