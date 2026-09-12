# Launchloom

**作った、その先まで。**

A local-first, open-source launch studio that turns a product brief and real
product footage into a film, a landing page, and reviewable social posts.

**v0.1.1 / single-operator alpha / provisional project name**

![Launchloom studio displaying a real generated sample](docs/screenshots/studio.png)

Astraを起動しなくても動く、独立したOSSです。企画・LP・実操作の収録・動画編集・
SNSの原稿・承認・配信・計測を、ひとつのキャンペーンとして扱います。
「制作画面だけ」のモックではなく、実際にMP4、HTML、投稿原稿、ZIPを出力します。

## いちばん早い試し方

必要：Python 3.11以降、FFmpeg/ffprobe、Chromium、日英フォント。
検証したバージョンは `requirements-tested.txt` を参照してください。

```bash
# macOS: FFmpegが未導入の場合
brew install ffmpeg

# このソースフォルダーの中で実行
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m playwright install chromium
cp .env.example .env
python -m launchloom serve
```

`http://127.0.0.1:8787` を開き、起動時にターミナルへ出たローカルアクセスキーで入室。
**「サンプルで試す」** を押してください。AI APIキーやSNSアカウントは不要です。

内蔵の小さなタスクアプリ「Orbit」を実際に操作し、横長・縦長動画、LP、原稿を制作します。
Orbitは実在サービスの実績を装うためのダミーではなく、このリポジトリ内で動くサンプルです。
出力にはサンプル表記が入ります。動画は音声素材未指定なら無音です。

### Smart Camera (v0.1.1)

自動収録では、クリックのたびにズームイン／ズームアウトする旧方式を廃止しました。
注視点をショットとして保持し、次の重要操作へだけ C2 連続の smootherstep で移動します。
近接した操作は同じショットにまとめ、画面端のクリックも安全領域へ寄せるため、
Screen Studioのような落ち着いた「意図のあるズーム」を狙っています。

- click: 1.17x / fill: 1.13x / scroll: 1.06x
- transition: 0.82s
- tiny retarget dead-zone: 7.5%
- zoom pulse / spring overshoot: なし

別ターミナルから開始する場合：

```bash
python -m launchloom doctor
python -m launchloom demo  # 先にserveを起動してください
```

Linuxでは `ffmpeg` と `fonts-noto-cjk` をOSのパッケージマネージャーで導入し、
`python -m playwright install --with-deps chromium` を使用してください。
Windowsではvenvの有効化は `.venv\Scripts\Activate.ps1` です。ffmpeg/ffprobeをPATHへ追加します。
macOS・Windows実機とDockerビルドはこの配布時点では未検証です。

## 自分のプロダクトで作る

画面右上からキャンペーンを作ります。プロダクト名、対象ユーザー、伝えること、公開先URL、
実装済み機能とその根拠を入力します。公開先URLがなくても制作できますが、登録用CTAは無効になります。

操作映像には3つの経路があります。

| 経路 | 内容 |
|---|---|
| ステージングURL | Playwrightがクリック・入力・スクロール・待機を実行。許可したoriginのみ。新規ブラウザコンテキストで、ログインCookieは引き継がない |
| アップロード / 画面収録 | 自分の動画、Screen Studio等で収録したMP4/WebM、デスクトップブラウザの画面共有からの録画を使用 |
| 紹介アニメーション | 操作映像がない場合のモーショングラフィックス。実画面収録ではないことを表示 |

URL収録の例は `examples/browser-capture.json`。`.env` の
`CAPTURE_ALLOWED_ORIGINS` にテスト環境のoriginを明示します。製品のログインや顧客情報を
自動で取り込む機能はありません。認証済み画面は安全なテストデータで手動収録してインポートします。
アップロードは200MB、300秒、各辺4096pxまで。編集で使用する操作素材は先頭最大20秒です。

企画・収録・編集中に変更を混ぜないため、完成キャンペーンは読み取り専用です。
変更する場合は新しいキャンペーンを作成してください。v0.1には自然言語による反復修正UI、
ドラッグ式の動画編集、全自動A/B最適化はありません。

## 出力

```text
launch-kit.zip
├── campaign.json        公開用の製品情報（根拠メモを除く）
├── storyboard.json      演出・シーン構成
├── landscape.mp4        16:9 / 1280×720 / H.264 / 24fps
├── portrait.mp4         9:16 / 720×1280 / H.264 / 24fps
├── landscape.jpg / portrait.jpg
├── captions.srt         画面上のシーン見出し。音声の文字起こしではない
├── posts.json / social-copy.md
├── qa.json              自動検査と限界・警告
├── manifest.json        ファイルハッシュと素材の出どころ
└── site/
    ├── index.html
    ├── site.css / site.js
    └── film.mp4 / poster.jpg
```

LPは自己完結した静的ファイルです。外部CDNや外部フォントの必須依存はありません。
自分の静的ホスティングへ `site/` の内容だけを公開できます。
このアプリ自体にはホスティングへの自動デプロイ機能はありません。

## 映像生成AIをつなぐ

ローカルのモーショングラフィックスと実画面収録だけなら、AI API料金はかかりません。
コンピューター、電力、ホスティング等のコストまでゼロという意味ではありません。

- **fal**：APIキー、モデルID、公式スキーマに沿った入力JSONを設定。
- **ComfyUI**：自分のサーバーと、信頼できるAPI形式の映像生成ワークフローを指定。
- **LLM**：Chat Completions互換エンドポイントで、企画の演出方針と映像プロンプトを作成。

いずれも必須依存ではありません。モデルを勝手に選択したり、重み・カスタムノードを
自動ダウンロードしたりしません。生成映像はコンセプト部分に使い、実際の製品機能の証拠には使いません。
送信前にUIで外部データ送信への同意が必要です。`docs/INTEGRATIONS.md` を参照してください。

## SNSへ届ける

**Postizを別のサービスとして連携**します。PostizのOAuth画面で自分のSNSを接続し、
Launchloomのサーバー環境に `POSTIZ_BASE_URL` と `POSTIZ_API_KEY` を設定します。

`ENABLE_LIVE_PUBLISH=0` が既定です。原稿の編集・コピー・送信JSONのdry-runは可能ですが、
外部に動画をアップロードしたり投稿したりはしません。

実投稿を使う場合は `ENABLE_LIVE_PUBLISH=1` に変更して再起動し、配信画面で投稿先を読み込みます。
原稿・動画・投稿先・権利の確認後に、**「承認して投稿」** または **「承認して予約」** を押します。
承認は原稿・メディアハッシュ・投稿先・予約日時・SNS固有設定に結び付きます。

対応アダプター：X、LinkedIn、Threads、Bluesky、YouTube、Instagram、TikTok。
ただし接続先Postizの対応、アカウント種別、API権限、各SNSの審査・制約に依存します。
YouTube/Instagram/TikTokでは投稿形式など追加設定が必要です。
全SNSの実アカウントで成功確認したという意味ではありません。

Postiz受付とSNS公開成功は別です。タイムアウトなどで結果が不明なら自動再送しません。
`needs_reconciliation` は管理者がPostiz側を確認する状態です。
ボットによる大量返信、DM、偽の反応購入、アカウント量産は実装していません。

## 構成

```text
Brief → Plan → Site → Capture → Concept film? → Render → QA / Launch kit
                                                           ↓
                                           Draft → Approval → Postiz
                                                           ↓
                                             Real metrics → Next brief
```

FastAPI / SQLite / Playwright / Pillow / FFmpeg / HTML+CSS+JavaScript。
フロントエンドのビルド工程や巨大なエージェントフレームワークを必須にしません。
APIによって他の製品から利用でき、Astraは将来の任意クライアントにできます。
詳細は `docs/ARCHITECTURE.md` と `docs/API.md`。

## 検証

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m compileall -q launchloom
```

`docs/VERIFICATION.md` に、実行結果・実ファイル・未検証範囲を分けて記録します。
自動検査の合格は、映像の芸術的完成度、機能主張の独立検証、バズ、売上、セキュリティ監査を意味しません。

## OSSと事業化

**今回のオリジナル実装はApache-2.0**。Postizやモデル等は別のライセンス・条件です。
`LICENSE` / `NOTICE` / `THIRD_PARTY.md` を確認してください。

OSS版はローカル制作・自分のキー・自分の投稿先を中核に維持。
将来の有料版候補はクラウドレンダリング、ブランド管理、チーム承認、素材管理、
投稿運用、公開・計測をまとめたホスティングです。これらは現版の実装済み機能ではありません。
具体的な次工程と完成条件を `docs/ROADMAP.md` に分けています。

**このalphaを認証付き画面ごとインターネットへ公開して、多人数SaaSとして運用しないでください。**
認証は単一操作者向けです。TLS・テナント分離・実行サンドボックス・ストレージ上限・
課金・監査・外部APIの実接続検証を行うまでは、信頼できるローカル環境に限定します。
