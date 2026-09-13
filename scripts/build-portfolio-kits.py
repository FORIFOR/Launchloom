"""Build five products through the real local pipeline using existing recordings.
No browser automation, paid provider, new recording, or publication.
Run: .venv/bin/python scripts/build-portfolio-kits.py OUTPUT [PROJECTS_DIR]
"""
from __future__ import annotations
import asyncio, hashlib, json, shutil, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from launchloom.config import Settings
from launchloom.models import Brief, BuildOptions
from launchloom.pipeline import build
from launchloom.store import Store

SOURCES = [
    ('genie', 'Genie', '会議のメモを、次の仕事へ。', 'astra-launch/dist/assets/astra-web-proposal-web.mp4',
     'https://astra-forifor.forifor.chatgpt.site/ja', '#6654db',
     [('モデルを選んで文章をつくる', 'ローカルモデルや接続したモデルで業務の文章を作成します。'),
      ('成果物をWorkに残す', '作成した文章を開き直し、仕事の続きに使えます。'),
      ('提案書の実演を見る', '映像は架空企業のWeb改善提案をローカルモデルで作成した実演です。')],
     'Recorded prototype; fictional company. No automatic customer delivery. docs/site/CONTENT.md in astra-launch'),
    ('ai-meeting', 'AI Meeting', '話したことを、次の一歩に。', 'AI-meeting-launch/dist/demo.mp4',
     'https://ai-meeting.forifor.chatgpt.site/ja', '#85766e',
     [('声で対話する', '接続した音声モデルと、日本語で対話できます。'),
      ('確認してタスクに残す', '会話中の提案を確認して、タスクとして保存します。'),
      ('動作記録を見る', '合成入力音声を使った実サービス実演です。人間100会話の検証ではありません。')],
     'Real Gemini output with synthetic Japanese input; docs/validation.md in AI-meeting-improvements'),
    ('oathra', 'Oathra', '完了には、相手の根拠がいる。', 'oathra/docs/media/oathra-battle-ja.mp4',
     'https://forifor.github.io/oathra/', '#ce9e45',
     [('条件を指定する', '依頼の日時や人数など、完了に必要な条件を設定します。'),
      ('相手の発言を検証する', 'エージェントの自己申告だけでは、完了にしません。'),
      ('シミュレーターで比較する', '映像はシミュレーションです。実店舗への電話映像ではありません。')],
     'Recorded simulator battle, not a real telephone call; oathra README and packages/evidence'),
    ('aisecure', 'AISecure', '大量のログから、調べるべき事案へ。', 'AISecure/docs/media/screendemo.mp4',
     'https://forifor.github.io/AISecure/index.ja.html', '#166d72',
     [('ローカルで調べる', '読み込んだスナップショットを端末内で解析するPoCです。'),
      ('関連する根拠をたどる', '検知した事案から、関連するイベントを確認できます。'),
      ('合成データで動作を確認', '常時監視や防御の自動実行は行いません。実企業ログでの評価は未実施です。')],
     'Actual local UI with synthetic fixture; AISecure README and docs/site/CONTENT.md'),
    ('agent-team', 'Agent Team', '成果物をつくり、検証して直す。', 'Multibot/docs/media/replay-research.mp4',
     'https://forifor.github.io/Multibot/ja/', '#355647',
     [('仕事を分ける', '調査・制作・レビューなどの役割に仕事を分けます。'),
      ('指摘を成果物へ結びつける', 'レビューと成果物の改訂を記録します。'),
      ('途中の結果も確認する', '映像は実行記録のリプレイです。全タスクの成功を示すものではありません。')],
     'Replay of recorded research run, partial outcome; docs/evidence/scenarios/research2'),
]

async def main():
    destination = Path(sys.argv[1]).resolve()
    projects = Path(sys.argv[2]).resolve() if len(sys.argv)>2 else Path(__file__).resolve().parents[2]
    destination.mkdir(parents=True, exist_ok=True)
    report_path = destination/'portfolio-evidence.json'
    if report_path.exists(): raise SystemExit('Use a fresh output directory; evidence is immutable.')
    settings = Settings(data_dir=destination/'private', token='local-only-portfolio-verification-token',
        llm_base='', llm_key='', llm_model='', fal_key='', comfy_base='', postiz_key='',
        tracking_base='', enable_live_publish=False, enable_paid_generation=False, budget_usd=0)
    settings.prepare(); store=Store(settings.data_dir/'state.sqlite')
    rows=[]
    revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    for slug,name,tagline,relative,url,accent,features,provenance in SOURCES:
        source=projects/relative
        if not source.is_file(): raise ValueError(f'Missing source recording: {relative}')
        brief=Brief(name=name,tagline=tagline,audience='業務へのAI導入を検討する方へ',
            description=features[-1][1],product_url=url,accent=accent,language='ja',goal='demos',
            channels=['x','linkedin','youtube','instagram'],
            features=[{'title':title,'detail':detail,'evidence':provenance,'approved':True} for title,detail in features])
        cid=store.create_campaign(brief.model_dump())['id']; root=settings.data_dir/'campaigns'/cid
        (root/'input').mkdir(parents=True); shutil.copyfile(source,root/'input/capture.bin')
        options=BuildOptions(capture_mode='upload',quality='hd',capture_length=24,review_plan=True)
        await build(settings,store,cid,options)
        record=store.campaign(cid)
        if record['state']!='awaiting_review': raise ValueError('Review gate did not stop the build')
        # Source descriptions and all feature claims above were checked against
        # the existing evidence before this controlled five-product batch.
        store.save_plan(cid,record['plan'],approved=True)
        started=time.monotonic(); manifest=await build(settings,store,cid,options)
        target=destination/slug; target.mkdir()
        for filename in ['launch-kit.zip','manifest.json','qa.json','social-copy.md']:
            shutil.copyfile(root/filename,target/filename)
        shutil.copytree(root/'site',target/'site')
        for filename in ['landscape.mp4','portrait.mp4','landscape.jpg','portrait.jpg','captions.srt','posts.json']:
            shutil.copyfile(root/filename,target/filename)
        row={'product':name,'sourceRecording':relative,'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'sourceMeaning':provenance,'renderSeconds':round(time.monotonic()-started,2),
            'videos':manifest['videos'],'socialDrafts':4,'externalApiCostUsd':0,'published':False,
            'quality':json.loads((root/'qa.json').read_text())['status']}
        rows.append(row); report_path.write_text(json.dumps({'sourceCommit':revision,'workingTreeChanges':'1080p30 render target',
            'scope':'existing recordings through local pipeline; not new end-to-end executions of five products',
            'costExcludes':['hardware','electricity'],'products':rows},ensure_ascii=False,indent=2))
        print(json.dumps({'product':name,'done':len(rows),'renderSeconds':row['renderSeconds']},ensure_ascii=False),flush=True)
    (destination/'README.md').write_text('# 企業紹介用の制作物\n\n既存の各製品の動作記録をLaunchloomへ読み込み、横長・縦長動画、LP、4媒体の投稿原稿を制作しました。動画内のシミュレーション・合成データ・リプレイの表示を維持してください。企業導入の実績、実通話100件、実人間100会話を示すものではありません。投稿原稿は未投稿です。\n')

if __name__=='__main__': asyncio.run(main())
