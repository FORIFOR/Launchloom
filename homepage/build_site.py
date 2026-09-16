"""Generate matched Japanese/English pages and a clearly scoped real UI demo.

No templates claim Seedance/Adobe/social execution was demonstrated. The recording
comes from tests/browser_flow.py with paid generation and live publishing disabled.
"""
from __future__ import annotations
import argparse
import html
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parent
D={
'ja':{
 'title':'仕上げた動画を、届けるところまで。',
 'description':'シーン構成、Seedance生成、AEへの制作引き渡し、完成動画の確認と配信を、ひとつのキャンペーンで。',
 'hero':'仕上げた動画を、<br>届けるところまで。',
 'intro':'録画も、生成映像も、AEの演出も。素材の作り方を整理し、完成した動画を確認して、投稿の準備まで進めます。',
 'nav':['出力例','実際の操作','対応範囲','使いはじめる'],
 'primary':'手元で試す','secondary':'実際の操作を見る','alt':'English',
 'note':'ローカル・1人用アルファ。外部AI・Adobe・投稿サービスの契約と料金は別です。',
 'film_label':'実際の出力例 / ローカル制作',
 'film_caption':'従来の録画・ローカル合成で作った紹介動画。SeedanceやAEによる作例ではありません。',
 'strip':['構成をつくる','素材を生成・編集','完成動画を確認','承認して配信'],
 'output_title':'ひとつの企画を、<br>届ける場所に合わせて。',
 'output_intro':'横長・縦長の動画、紹介ページ、投稿案。同じキャンペーンの中で、次に使うものが揃います。',
 'output_items':[('横長と縦長','録画からの制作では、16:9と9:16をそれぞれの構成で書き出します。'),('編集済みの動画も','AEなどで完成させたMP4・MOV・WebMを取り込み。勝手に字幕や演出を追加しません。'),('紹介ページと投稿案','ローカル制作のページ例と、7媒体の投稿下書きを確認できます。')],
 'page_link':'紹介ページの実ファイルを見る ↗','kit_link':'完成サンプル一式を開く ↓','sample_link':'制作パッケージの例を開く ↓',
 'workflow_title':'作る。見直す。<br>そのまま、配信の準備へ。',
 'workflow_intro':'実際のローカルアプリで、構成の編集、動画の取り込み、採用、投稿プレビューまで操作しました。',
 'workflow_caption':'実UIの操作記録 / テスト用キャンペーンと既存の動画素材を使用。Seedance・Codex・Claude Code・Adobeは呼び出していません。SNSへの送信はゼロです。',
 'feature_cards':[('シーンごとに、作り方を選ぶ。','実録画、Seedance、AE。秒数と演出指示を保存し、Seedanceは内容と費用を確認してから生成を依頼。失敗時は保存された依頼を照合します。'),('仕上がりを、版で管理する。','原本を残したまま、配信用MP4とプレビューを用意。採用する版を変えると未送信の古い承認を無効にし、確認を取り直します。'),('公開は、最後の一操作。','動画・投稿文・アカウント・日時を確認。Postizへの受付と、SNSでの公開状態を分けて記録します。')],
 'status_title':'対応範囲を、曖昧にしない。','status_intro':'実装と実機確認は別です。使う前に、必要な環境が分かります。',
 'headers':['機能','この版の対応','必要な環境・検証範囲'],
 'rows':[
 ('録画から動画・紹介ページ・投稿案','ローカル制作','既存機能。外部AIなしの経路を利用できます。'),
 ('完成動画 → 確認 → 投稿準備','実装・自動テスト','MP4/MOV/WebM。実UIで取り込みから送信なしのプレビューまで検証。'),
 ('Seedance 2.5','シーン生成API接続','falキーと有料生成の許可が必要。実課金による生成品質は未検証。'),
 ('Codex / Claude Code','制作指示 + ローカルCLI','JSX候補を生成するコマンド。APIキーとCLIのインストールが必要。実モデル呼び出しは未検証。'),
 ('After Effects','JSX + ローカルCLI','WindowsのJSX呼び出しとaerenderコマンド。macOSのJSX実行はAEから手動。ライセンス・実機検証が必要。'),
 ('Postizによる投稿・予約','承認付きAPI接続','送信・二重送信防止はテスト用接続で検証。実SNSアカウントでの公開は未検証。')],
 'draft_title':'7媒体の投稿下書きを見る','draft_note':'すべて未投稿の例です。投稿前に内容・権利・投稿先を確認してください。',
 'start_title':'まずは、自分の動画を一本。','start_intro':'初回セットアップ後、「シーン・完成動画」を開きます。完成動画の取り込みとプレビューは、外部AIやSNSアカウントを接続する前にも使えます。',
 'steps':['READMEの手順でインストール','スタジオを起動してアクセスキーで接続','企画を作り、シーン編集か完成動画の取り込みへ'],
 'docs':'詳しい制作フローを見る ↗','feedback':'使ってみた結果を伝える ↗','skip':'本文へ移動',
 'zip_note':'サンプルには構成データ・生成指示・AE用JSXを収録。完成したAEプロジェクトや、有料生成の素材は含みません。',
},
'en':{
 'title':'From a finished film to a reviewed post.',
 'description':'Plan scenes, request Seedance footage, hand off motion graphics, and bring finished films back for review and distribution.',
 'hero':'Your film is finished.<br>Keep the launch moving.',
 'intro':'Real recordings, generated footage, and motion graphics. Organize the scenes, bring back the finished film, and prepare a post with the exact version you reviewed.',
 'nav':['Outputs','See the workflow','Capabilities','Get started'],
 'primary':'Try it locally','secondary':'Watch the real workflow','alt':'日本語',
 'note':'Local, single-operator alpha. External AI, Adobe, and publishing accounts and fees are separate.',
 'film_label':'ACTUAL OUTPUT / LOCAL RENDER',
 'film_caption':'An existing film from the recording and local-render path. Not a Seedance or After Effects production example.',
 'strip':['Plan scenes','Generate & edit','Review the film','Approve distribution'],
 'output_title':'One campaign.<br>More than one format.',
 'output_intro':'Landscape and portrait films, a landing page, and channel-specific drafts. Keep the work together as it moves toward release.',
 'output_items':[('Landscape and portrait','The recording workflow builds separate 16:9 and 9:16 compositions.'),('Finished elsewhere? Bring it back.','Import a finished MP4, MOV, or WebM from AE or another editor. No unsolicited titles, effects, or creative changes.'),('A page and drafts, too','Open an actual locally generated page and inspect drafts for seven channels.')],
 'page_link':'Open the generated page ↗','kit_link':'Explore the existing launch kit ↓','sample_link':'Inspect a production handoff sample ↓',
 'workflow_title':'Make it. Review it.<br>Prepare it for publication.',
 'workflow_intro':'A real local-app recording: edit the plan, import a film, select a reviewed version, and preview a publication without sending it.',
 'workflow_caption':'ACTUAL UI RECORDING / A test campaign with existing sample media. No Seedance, Codex, Claude Code, or Adobe execution. No social post was sent.',
 'feature_cards':[('Choose a tool for each scene.','Recording, Seedance, or AE. Save durations and directions. Seedance requests need data and cost confirmation; retries reconcile the stored job.'),('Keep the exact version you reviewed.','Import without changing your original. Selecting a different film invalidates old unsent approvals and holds the campaign for a fresh release decision.'),('Make publishing a separate decision.','Review the film, copy, account, and time. Postiz acceptance and confirmed social publication are tracked separately.')],
 'status_title':'Clear capabilities. Clear boundaries.','status_intro':'Implemented does not mean tested against every external service. Here is what this build actually includes.',
 'headers':['Capability','This build','Requirements and verification'],
 'rows':[
 ('Recording → film, page and drafts','Local production','Existing workflow; external AI is optional.'),
 ('Finished film → review → publication draft','Implemented & tested','MP4/MOV/WebM. Actual browser flow through import, selection and a no-send preview.'),
 ('Seedance 2.5','Scene generation API adapter','Requires a fal key and paid-generation permission. Paid output quality is not live-verified.'),
 ('Codex / Claude Code','Handoff + local CLI','Commands generate candidate JSX. Requires an installed CLI and API key. Live model execution is not verified.'),
 ('After Effects','JSX + local CLI','Windows JSX invocation and aerender command. On macOS, run JSX manually in AE. Requires licensed Adobe software and real-machine verification.'),
 ('Postiz publishing & scheduling','Approval-gated API adapter','Submission and duplicate prevention tested with a fake publisher. Real social-account publication is not verified.')],
 'draft_title':'Inspect seven channel drafts','draft_note':'Unpublished examples. Check the content, rights, and destination before posting.',
 'start_title':'Start with a film you already have.','start_intro':'After setup, open Scenes & finished films. Import and review a finished video before connecting an external AI or social account.',
 'steps':['Install using the README','Start the studio and enter its local access key','Create a campaign and plan scenes or import a finished film'],
 'docs':'Read the production workflow ↗','feedback':'Share your test results ↗','skip':'Skip to content',
 'zip_note':'The sample contains a plan, creative instructions, and AE JSX. No completed Adobe project or paid-generated media is bundled.',
}}


def page(language:str,drafts:list[dict]):
    d=D[language];ja=language=='ja';root='../' if ja else '';alt='../' if ja else 'ja/'
    esc=html.escape;repo='https://github.com/FORIFOR/Launchloom';url='https://forifor.github.io/Launchloom/'+('ja/' if ja else '')
    nav=''.join(f'<a href="#{id}">{esc(label)}</a>' for id,label in zip(['outputs','workflow','capabilities','start'],d['nav']))
    strip=''.join(f'<span><small>0{i+1}</small>{esc(v)}</span>' for i,v in enumerate(d['strip']))
    outputs=''.join(f'<article><h3>{esc(a)}</h3><p>{esc(b)}</p></article>' for a,b in d['output_items'])
    features=''.join(f'<article><span class="index">0{i+1}</span><h3>{esc(a)}</h3><p>{esc(b)}</p></article>' for i,(a,b) in enumerate(d['feature_cards']))
    rows=''.join('<tr>'+''.join(f'<td>{esc(c)}</td>' for c in row)+'</tr>' for row in d['rows'])
    draft_html=''.join('<li><span class="ch">'+esc(x['channel'])+'</span><pre>'+esc(x['content'])+'</pre></li>' for x in drafts)
    steps=''.join(f'<li>{esc(v)}</li>' for v in d['steps']);headings=''.join(f'<th scope="col">{esc(v)}</th>' for v in d['headers'])
    readme=repo+('/blob/main/README.ja.md' if ja else '#readme')
    return f'''<!doctype html>
<html lang="{language}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Launchloom — {esc(d['title'])}</title><meta name="description" content="{esc(d['description'],quote=True)}">
<meta name="theme-color" content="#182019"><link rel="canonical" href="{url}">
<link rel="alternate" hreflang="en" href="https://forifor.github.io/Launchloom/"><link rel="alternate" hreflang="ja" href="https://forifor.github.io/Launchloom/ja/">
<meta property="og:type" content="website"><meta property="og:title" content="Launchloom — {esc(d['title'],quote=True)}"><meta property="og:description" content="{esc(d['description'],quote=True)}"><meta property="og:url" content="{url}"><meta property="og:image" content="https://forifor.github.io/Launchloom/workflow-poster.jpg"><meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="{root}site.css"><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect x='6' y='4' width='20' height='24' rx='4' fill='%23e69c73'/%3E%3C/svg%3E">
</head><body><a class="skip" href="#main">{esc(d['skip'])}</a>
<header class="hero"><div class="shell"><nav aria-label="Main"><a class="brand" href="./"><i aria-hidden="true"></i>launchloom</a><div class="nav-links">{nav}<a class="language" href="{alt}">{d['alt']}</a></div></nav>
<div class="hero-grid"><div><p class="eyebrow">OPEN SOURCE / LOCAL-FIRST</p><h1>{d['hero']}</h1><p class="lede">{esc(d['intro'])}</p><div class="actions"><a class="button primary" href="#start">{esc(d['primary'])} ↗</a><a class="button outline" href="#workflow">{esc(d['secondary'])}</a></div><p class="fine">{esc(d['note'])}</p></div>
<figure class="film"><div class="frame-bar"><span>{esc(d['film_label'])}</span><span>16:9</span></div><video controls playsinline preload="none" poster="poster.jpg" src="film.mp4"><track kind="captions" src="captions.vtt" srclang="{language}" label="{language}"></video><figcaption>{esc(d['film_caption'])}</figcaption></figure></div>
<div class="flow-strip">{strip}</div></div></header>
<main id="main"><section id="outputs"><div class="shell"><div class="heading"><div><p class="eyebrow">THE OUTPUTS</p><h2>{d['output_title']}</h2></div><p>{esc(d['output_intro'])}</p></div><div class="output-grid"><figure class="portrait"><video controls playsinline preload="none" src="film-vertical.mp4" poster="poster-vertical.jpg"><track kind="captions" src="captions.vtt" srclang="{language}" label="{language}"></video><figcaption>9:16 / LOCAL OUTPUT</figcaption></figure><div class="output-list">{outputs}<div class="text-links"><a href="kit-site/index.html" target="_blank" rel="noopener">{esc(d['page_link'])}</a><a href="launch-kit.zip" download>{esc(d['kit_link'])}</a></div></div></div></div></section>
<section id="workflow" class="workflow"><div class="shell"><div class="heading"><div><p class="eyebrow">ACTUAL WORKFLOW / NO EXTERNAL POST</p><h2>{d['workflow_title']}</h2></div><p>{esc(d['workflow_intro'])}</p></div><figure class="workflow-film"><video controls playsinline preload="none" src="{root}workflow.mp4" poster="{root}workflow-poster.jpg"><track kind="captions" src="{root}workflow-{language}.vtt" srclang="{language}" label="{language}"></video><figcaption>{esc(d['workflow_caption'])}</figcaption></figure><div class="features">{features}</div><div class="handoff-link"><a href="{root}production-sample.zip" download>{esc(d['sample_link'])}</a><p>{esc(d['zip_note'])}</p></div></div></section>
<section id="capabilities"><div class="shell"><div class="heading"><div><p class="eyebrow">WHAT IS READY</p><h2>{esc(d['status_title'])}</h2></div><p>{esc(d['status_intro'])}</p></div><div class="table-scroll" role="region" aria-label="Capabilities" tabindex="0"><table><thead><tr>{headings}</tr></thead><tbody>{rows}</tbody></table></div></div></section>
<section id="posts"><div class="shell"><p class="eyebrow">CHANNEL-SPECIFIC DRAFTS</p><details><summary>{esc(d['draft_title'])}</summary><p>{esc(d['draft_note'])}</p><ul class="drafts">{draft_html}</ul><template data-caption="posts">{esc(d['draft_note'])}</template></details></div></section>
<section id="start" class="start"><div class="shell start-grid"><div><p class="eyebrow">YOUR NEXT FILM</p><h2>{esc(d['start_title'])}</h2><p>{esc(d['start_intro'])}</p><div class="actions"><a class="button primary" href="{readme}">GitHub / {esc(d['primary'])} ↗</a><a href="{repo}/blob/main/docs/PRODUCTION_WORKFLOW.md">{esc(d['docs'])}</a></div></div><div><ol>{steps}</ol><pre><code>python -m launchloom serve</code></pre><a href="{repo}/issues">{esc(d['feedback'])}</a></div></div></section></main>
<footer><div class="shell"><span>Launchloom / Apache-2.0</span><span><a href="{repo}">GitHub</a> · <a href="{repo}/blob/main/docs/SECURITY.md">Security</a> · <a href="{repo}/blob/main/docs/PRODUCTION_WORKFLOW.md">Verification</a></span></div></footer></body></html>
'''


def build(recording:Path|None=None,output:Path=ROOT):
    from homepage.refresh_post_samples import build_samples
    from launchloom.production import build_bundle,initial_plan
    output.mkdir(parents=True,exist_ok=True);(output/'ja').mkdir(exist_ok=True)
    samples=build_samples()
    for lang in ['ja','en']:
        path=output/('ja/index.html' if lang=='ja' else 'index.html')
        path.write_text(page(lang,samples[lang]),encoding='utf-8')
    if output!=ROOT:shutil.copyfile(ROOT/'site.css',output/'site.css')
    (output/'production-sample.zip').write_bytes(build_bundle(initial_plan({'name':'Launchloom','tagline':'From a film to a reviewed post','features':[]})))
    (output/'post-drafts.json').write_text(json.dumps({'scope':'Unpublished draft examples','drafts':samples},ensure_ascii=False,indent=2))
    if recording:
        clips=list((recording/'recording').glob('*.webm'))
        if len(clips)!=1:raise ValueError('Exactly one successful browser recording is required')
        report=json.loads((recording/'report.json').read_text())
        if not all(report.get(k) is True for k in ['onboarding_to_board','scene_edit_save_export','real_mp4_import_review_select','publication_dry_run_and_live_gate','campaign_context_roundtrip','no_mobile_overflow']):raise ValueError('Browser acceptance did not pass')
        if report['page_errors'] or report['external_requests'] or report['external_posting']:raise ValueError('Demo must not contain failed interactions or external calls')
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(clips[0]),'-vf','scale=1280:-2','-an','-c:v','libx264','-preset','fast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',str(output/'workflow.mp4')],check=True,timeout=180)
        # Use a real frame from the successful recording, not a fictional UI image.
        subprocess.run(['ffmpeg','-v','error','-y','-ss','3','-i',str(output/'workflow.mp4'),'-frames:v','1',str(output/'workflow-poster.jpg')],check=True,timeout=30)
        for lang in ['ja','en']:
            text=D[lang]['workflow_caption']
            (output/f'workflow-{lang}.vtt').write_text('WEBVTT\n\n00:00:00.000 --> 00:05:00.000\n'+text+'\n',encoding='utf-8')
        (output/'workflow-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--recording',type=Path);parser.add_argument('--output',type=Path,default=ROOT)
    args=parser.parse_args();build(args.recording,args.output)
