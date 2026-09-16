# Production handoff / 制作引き渡し

The scene editor, finished-film import, and publication bridge now share one campaign.
See **[PRODUCTION_WORKFLOW.md](PRODUCTION_WORKFLOW.md)** for setup, current capabilities,
Seedance jobs, local Codex/Claude Code/Adobe commands and verification boundaries.

The handoff ZIP itself still contains exactly six text files: `production.json`,
`seedance-prompts.md`, `AGENT_TASK.md`, `build.jsx`, `assets/README.txt`, and `README.md`.
It does not contain credentials, private evidence, recordings, or generated footage.
The default JSX creates a basic editable timeline; it does not itself interpret the
creative prompt. Exporting this ZIP does not call any external provider or publish.

日本語: 通常スタジオの「シーン・完成動画」から開けます。ZIPを出すだけでは有料生成や
AE実行は行いません。生成は別の明示操作、完成動画の取り込みと採用は別の確認工程です。
