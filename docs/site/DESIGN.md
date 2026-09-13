# Launchloom — design
Charcoal studio, warm coral control, finished product media as the main surface. Maximum content width 1240px, body 18px, controls 48px. Human playback, no autoplay or decorative motion.
Reference: https://developers.openai.com/showcase/frame-studio — media and controls form one experience, rather than a background film.
Three compositions use identical copy and media: A balanced split; B centered copy over a full-width player; C compact left copy and a two-thirds artifact stage. Candidates are stored under docs/site/candidates. C is the implementation candidate because the real interface stays readable while the main action remains beside it. The comparison result is below.

## Comparison result
1440×1000 in the native browser: A media width 600px / top138px; B 1240px / top618px; C 792px / top138px. Adopt C: 32% more media width than A, while the full player and action remain visible; B pushes the image below most of the first viewport. These are layout measurements, not conversion claims.
