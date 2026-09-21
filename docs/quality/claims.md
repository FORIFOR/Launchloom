# Claims mapped to implementation

Audit scope: baseline `cb0372631e8128f5517a28e4ae17c4979d14f846` plus the local
changes indexed in [verification.md](verification.md). Claims below distinguish
implemented code from execution evidence; a test double is not a live provider.

| Claim / surface | Implementation | Verification / limit |
|---|---|---|
| One brief produces two films, LP and social drafts | `pipeline.py`, `rendering.py`, `site.py`, packaging and manifest code | PASS: real local sample, edited SRT, both full MP4 decodes, LP playback, ZIP hashes; see browser and independent reports |
| Editable sample | `/api/demo?review_plan=true`, bundled Orbit app recording, standard review editor | PASS: labelled sample, durable review, explicit approval. Orbit is demonstration footage, not footage of the user's product |
| Human review before generation | Standard pipeline review occurs before film rendering | Corrected: optional consented planning LLM can already have run before review. Local sample disables providers; it has no generated voice/music |
| Scene edits update all deliverables | Standard editor edits plan captions/titles; LP/social copy derives from Brief | Corrected: standard scene edits affect film/storyboard/SRT; LP/social synchronization belongs to experimental creative workflow. No universal synchronization claim |
| HD output | Standard renderer 1920×1080 / 1080×1920, 30fps; draft 960×540 / 540×960 | PASS: actual exports decoded. V2 creative renderer separately uses 1280×720 / 720×1280, 24fps; stale standard UI/Japanese docs corrected |
| API can safely resume | Store transactional creation key, authenticated OpenAPI, HTTP client campaign/key options | PASS: concurrent key replay, 409 conflicts, real response loss, SDK resume and ZIP verification. Single local operator/process; not a multi-tenant service or stable Python SDK |
| AI/provider, Postiz, deployment and Adobe integration | Existing adapters, consent/approval/reconciliation and provider-specific logic | Implemented, with local regression tests/test doubles. BLOCKED for live external execution this turn: no authorization for transmission, spending, publishing or licensed Adobe execution |
| Worker recovery | Store marks unfinished jobs interrupted at startup; operator explicitly retries | PASS: actual test process-group termination during FFmpeg, restart and same-campaign completion. No claim that unknown external side effects can safely be repeated |
| Selective regeneration | Experimental v2 creative fingerprints/reuse; standard revision recomposes stored material | Documentation aligned; full v2 UX/provider validation is outside the selected local studio task |
| Human product superiority / first-time user success rate | No comparative user study in this repository run | BLOCKED: no recruited novices or equivalent competitor trial. Automated elapsed time is host-specific and not a human success metric |

The historical README animation is labelled as the prior automatic-demo flow.
The current flow is documented in README, FIRST_PROOF and the acceptance task.
No requested custom quality Skill was installed; none is claimed as used.
