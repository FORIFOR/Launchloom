# Horio Premium Web — Launchloom application

Launchloom uses the Horio Premium Web standard with one product-specific signature: an **aperture reveal around the real film output**.

## What is shared

- Warm paper background `#F6F5F0`, charcoal type `#20251F`, deep product stage `#171A17`.
- One restrained accent `#A83B2F` for identity and decisive actions.
- Large Japanese/English typography, generous whitespace and editorial composition instead of decorative card walls.
- Real product footage and generated artifacts are the dominant visual evidence.
- No blue-purple AI gradients, glow, glass, particles, meaningless 3D objects, or bento-only layouts.

## Launchloom-specific signature moment

Only the hero's real-output stage moves. When it becomes visible, the film expands from a narrow cinematic aperture to the full real product frame. The rest of the page remains still. With `prefers-reduced-motion` or `.motion-off`, the complete frame is shown immediately.

## Evidence rules

Public UI must label actual footage/output as actual. Design previews must be labeled separately. Do not add customer logos, reviews, benchmark numbers, company claims, or unverified automation.

## Required pre-publish checks

`homepage/check.py` verifies 1440px, 1024px, and 390px and records screenshots for:

- Logo Swap Test
- Screenshot Test with motion disabled
- first-view service clarity
- real product/output dominance
- one Signature Moment only
- no horizontal overflow
- actual film playback on request

Static regression tests live in `tests/test_horio_premium_homepage.py`.
