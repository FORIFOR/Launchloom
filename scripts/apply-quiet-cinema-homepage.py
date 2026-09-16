from pathlib import Path

EN = r"""
/* Quiet Cinema — public site */
:root{--ink:#20251F;--ink-soft:#20251F;--paper:#F6F5F0;--card:#FBFAF6;--line:#D8D7CF;--muted:#62685F;--accent:#A83B2F;--green:#566454;--dark-ink:#F5F3EC;--dark-muted:#B8BDB2;--dark-line:#343832}
body{background:var(--paper);color:var(--ink);font-size:17px}
.hero{background:var(--paper);color:var(--ink);padding-bottom:clamp(58px,8vw,96px)}
.hero::after{display:none}.hero h1{color:var(--ink);font-size:clamp(2.8rem,6.3vw,5.1rem);line-height:1.04;max-width:9.5ch}
.hero .lede,.hero .eyebrow,.hero .note{color:var(--muted)}.nav-links{color:var(--muted)}.nav-links a:hover{color:var(--ink)}
.mark{background:var(--accent);border-radius:4px}.hero-grid{grid-template-columns:minmax(0,.68fr) minmax(0,1.32fr);gap:clamp(32px,5vw,72px);align-items:center}
.btn{border-radius:8px;transition:background .16s ease,border-color .16s ease}.btn:hover{transform:none}.btn-primary{background:var(--accent);color:#FFF9F4}.btn-primary:hover{background:#8F3027}.btn-ghost{border-color:var(--line);color:var(--ink)}.btn-ghost:hover{border-color:#B6B5AD;background:#EEECE5}
.showcase{background:#171A17;border-radius:16px;padding:18px;box-shadow:none}.showcase-tabs{border-color:#353934}.tab{color:#AEB4A9}.tab[aria-selected="true"]{color:#F5F3EC;background:#262A26}.stage{background:#171A17}.frame{background:#0E100E;border-color:#343832;border-radius:12px;box-shadow:0 28px 90px rgba(0,0,0,.28)}.caption,.stage-foot{color:#B8BDB2}
section{border-top:1px solid var(--line)}.card{background:transparent;border:0;border-top:1px solid var(--line);border-radius:0;padding-inline:0}.card .num{color:var(--accent)}
.dogfood,.refuse,.camera,.start{background:var(--paper);color:var(--ink);border-top:1px solid var(--line)}.dogfood .section-head p,.dogfood .eyebrow,.camera .eyebrow,.camera p,.camera figcaption,.refuse .eyebrow,.refuse-item p,.start p{color:var(--muted)}.bug{color:var(--muted);border-left-color:var(--accent)}.bug b,.camera h2,.camera-figures b{color:var(--ink)}.camera-figures,.camera-figures div,.refuse-item{border-color:var(--line)}.camera-figures div{color:var(--muted)}
.narrated{background:var(--paper);border-color:var(--line)}.narrated .frame,.camera video{background:#171A17;border-radius:16px;border-color:#343832}.wrote-shot,.excerpt{background:transparent;border-color:var(--line);box-shadow:none}.kit-list,.kit-row{border-color:var(--line)}
pre{background:#171A17;color:#F5F3EC;border-radius:12px}.copy{background:#2A2E2A;color:#F5F3EC;border-color:#3D433D}.btn-dark{background:var(--accent);color:#FFF9F4}.start code{background:#ECE9E1;color:var(--ink)}
:focus-visible{outline:3px solid var(--accent)!important;outline-offset:4px}
@media(max-width:900px){.hero-grid{grid-template-columns:minmax(0,1fr)}.hero h1{max-width:12ch}.showcase{padding:12px}}
"""

JA = r"""
/* Quiet Cinema — 公開サイト */
:root{--ink:#20251F;--paper:#F6F5F0;--muted:#62685F;--line:#D8D7CF;--accent:#A83B2F;--light:#B8BDB2;--stage:#171A17;--stage-ink:#F5F3EC}
body{background:var(--paper);color:var(--ink)}.hero{background:var(--paper);color:var(--ink);padding-bottom:72px}.hero .eyebrow,.hero .intro,.hero .meta{color:var(--muted)}
.hero-grid{grid-template-columns:minmax(0,.7fr) minmax(0,1.3fr);gap:clamp(34px,5vw,76px)}.hero h1{font-size:clamp(40px,5.6vw,72px);line-height:1.12;max-width:8.8em}.mark{background:var(--accent);border-radius:4px}
nav .links{color:var(--muted)}.button{border-radius:8px;border-color:var(--line)}.button.primary{background:var(--accent);border-color:var(--accent);color:#FFF9F4}.video-frame{background:var(--stage);border-color:#343832;border-radius:16px;box-shadow:0 28px 90px rgba(0,0,0,.24);padding:12px}.video-frame video{border-radius:10px;background:#0E100E}.video-bar,.hero figcaption{color:var(--light);border-color:#343832}
section{border-top:1px solid var(--line);border-bottom:0}.steps article,.output-row{border-color:var(--line)}.production{background:var(--paper)}.board{background:transparent;border-inline:0;border-radius:0}.board-head,.board-row{border-color:var(--line)}.board-row{padding-inline:0}.scope>div{border-left-color:var(--accent)}.drafts{grid-template-columns:1fr}.drafts li{background:transparent;border-inline:0;border-bottom:0;border-radius:0;padding-inline:0}.drafts li+li{border-top:1px solid var(--line)}
.start{background:var(--paper);color:var(--ink);border-top:1px solid var(--line)}.start .eyebrow,.start p{color:var(--muted)}.start code{background:#ECE9E1;color:var(--ink)}.start-aside{border-left-color:var(--line)}
:focus-visible{outline:3px solid var(--accent);outline-offset:5px}
@media(max-width:900px){.hero-grid{grid-template-columns:1fr}.hero h1{max-width:11em}}
"""

def patch(path: str, css: str, replacements: list[tuple[str,str]], marker: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if marker not in text:
        if '</style>' not in text:
            raise SystemExit(f'{path}: no style close')
        text = text.replace('</style>', css + '\n</style>', 1)
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new, 1)
        elif new not in text:
            raise SystemExit(f'{path}: expected copy not found: {old[:50]}')
    p.write_text(text, encoding='utf-8')

patch('homepage/index.html', EN, [
    ('<h1>Your product.<br>A launch worth seeing.</h1>', '<h1>Built to be seen.</h1>'),
    ('One brief and one real recording of your product become a\n        film, a vertical cut, a landing page and reviewable social posts — from\n        the same plan, on your own machine.', 'One campaign keeps the real product, the finished film, the landing page and reviewable posts together — from first recording to the moment you are ready to publish.'),
], '/* Quiet Cinema — public site */')

patch('homepage/ja/index.html', JA, [
    ('<h1>操作録画を、<br>紹介動画と<br>投稿案に。</h1>', '<h1>作ったものを、<br>届けられる形へ。</h1>'),
    ('ひとつの企画から、横動画、縦動画、紹介ページへ。外部で仕上げた動画も取り込んで、プレビュー・投稿文・公開前の確認まで、一つの企画のまま進めます。', '実際の画面を録り、一本の映像に整え、仕上げた動画をそのまま投稿準備へ。画面は静かに。製品は、鮮やかに。'),
], '/* Quiet Cinema — 公開サイト */')
