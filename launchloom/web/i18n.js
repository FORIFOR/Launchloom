// The studio was written in Japanese. Rather than rewrite 230 call sites and risk
// breaking a UI that works, this translates the rendered DOM: exact text nodes and
// a few attributes, looked up in the table below. Replacing Japanese with English
// makes a node stop matching, so running it repeatedly is harmless.
//
// Adding a language means adding a table. Anything missing simply stays Japanese,
// which is a legible failure rather than a broken screen.
//
// Values are written into text nodes, so they hold real characters — \u00a0 for a
// non-breaking space — never HTML entities, which would show up literally.

const EN = {
  'シーン・完成動画': 'Scenes & finished films',
  '録画から紹介動画を作る': 'Make a film from a recording',
  'シーン制作・完成動画の取り込みへ進む': 'Plan scenes or import a finished film',
  '配信する動画': 'Film to publish',
  'SNS固有設定': 'Platform settings',

  // — shell, navigation, campaign bar —
  'Launchloom — 作った、その先まで。': 'Launchloom — from a product to a launch',
  '作った、その先まで': 'You built it. Now show it',
  '作った、その先まで。': 'You built it. Now show it.',
  'ひとつの企画から、映像・サイト・届け方まで。': 'One brief. A film, a page, and a way to reach people.',
  '制作スタジオ': 'Studio',
  'ランディングページ': 'Landing page',
  '配信・承認': 'Distribution',
  '実測・改善': 'Results',
  '制作ログ': 'Activity',
  '新しいキャンペーン': 'New campaign',
  '最初のキャンペーン': 'Your first campaign',
  'サンプルで試す ↗': 'Try the sample ↗',
  '自分のサーバー。自分の素材。': 'Your machine. Your material.',
  '＋ &nbsp; キャンペーンをつくる': '＋ \u00a0 New campaign',
  'いいプロダクトを、': 'Good work',
  '見つけてもらえるところまで。': 'deserves to be found.',
  '外部投稿は承認後のみ': 'Approval required',
  '接続状態': 'Connections',
  '接続設定': 'Connection settings',

  // — pipeline stages —
  '企画・方向性': 'Brief & direction',
  '操作収録': 'Capture',
  '映像・パッケージ': 'Film & kit',
  '承認・配信': 'Approve & send',
  '構成の確認待ち': 'Waiting for review',
  '企画': 'Brief',
  'LP制作': 'Landing page',
  '映像生成': 'Generation',
  '映像編集': 'Editing',
  '梱包・検証': 'Packaging',
  '品質確認': 'Quality checks',
  '制作完了': 'Ready',
  '制作待ち': 'Queued',
  '制作中': 'Building',
  '下書き': 'Draft',
  '要確認': 'Needs attention',
  '中断': 'Interrupted',
  '承認済み': 'Approved',
  '送信中': 'Sending',
  'Postiz受付済み': 'Accepted by Postiz',
  '送信結果を要確認': 'Outcome unknown',
  '未作成': 'Not started',

  // — access dialog —
  'おかえりなさい。': 'Welcome back.',
  '起動したターミナルに表示されたアクセスキーを入力してください。APIキーとは別の、ローカル専用キーです。':
    'Enter the access key printed in the terminal where you started the studio. It is a local key, not an API key for any service.',
  'アクセスキー': 'Access key',
  'スタジオを開く ↗': 'Open the studio ↗',

  // — film tab —
  '◫ &nbsp; プロダクトフィルム': '◫ \u00a0 Product film',
  '映像も、サイトも、その先の広がりも。': 'The film, the page, and everything after.',
  'いいものを、\n見過ごされないものに。': 'Good work,\nfinally seen.',
  'いいものを、': 'Good work,',
  '見過ごされないものに。': 'finally seen.',
  '企画から実ファイルを制作しています。': 'Producing real files from your brief.',
  'レンダリング完了後に実際の動画を表示します。': 'The actual film appears here once it renders.',
  '未作成 · サンプルで、制作の一連を試す ↗': 'Nothing yet · run the bundled sample end to end ↗',
  '実ファイル生成済み · 公開前に映像を確認してください。': 'Real files produced · watch the film before anything goes out.',
  'ローカル制作には生成AIのAPIキーは不要です。': 'Producing locally needs no AI API key.',
  '制作キットを書き出す ↓': 'Download the launch kit ↓',
  '最初の企画をつくる ↗': 'Write your first brief ↗',
  'いい映像に、いい入口を。': 'A good film deserves a good doorway.',
  'ひとつの企画、いくつもの届け方。': 'One brief, many ways to arrive.',
  '同じトーンのLPと、投稿原稿もできています。': 'The landing page and the drafts are in the same voice.',
  'まずは内蔵サンプルを動かして、実際の制作物を確認。': 'Run the bundled sample and look at what comes out.',
  'LPを見る': 'See the page',
  '配信のしくみ': 'How sending works',
  '心を動かす、最初の3秒。': 'The first three seconds.',
  '本当に動くところを見せる。': 'Show it actually working.',
  '次の一歩につなげる。': 'Point at the next step.',
  '伝わる。\nそのあとに、動きたくなる。': 'Understood first.\nWanted second.',
  '伝わる。': 'Understood first.',
  'そのあとに、動きたくなる。': 'Wanted second.',
  '華やかさだけで終わらせず、実際の機能を、使う場面へつなげます。':
    'Not spectacle for its own sake: real features, shown in the moment they are used.',
  'プロダクト': 'Product',
  '映像の入力': 'Footage',
  '生成エンジン': 'Engine',
  'アクセント': 'Accent',
  '内蔵の実動作アプリ': 'Bundled working app',
  'Playwright 自動収録': 'Playwright capture',
  '収録・アップロード': 'Recorded / uploaded',
  '機能紹介アニメーション': 'Motion graphics',
  '確認済みの機能だけを紹介': 'Only features you verified',
  'APIキーはブラウザに渡さない': 'API keys never reach the browser',
  '外部投稿には別途、明示承認が必要': 'Sending anywhere needs its own approval',
  '未設定': 'Not set',

  // — review gate —
  '◫ &nbsp; 届ける前に、構成を確かめる。': '◫ \u00a0 Read it before it renders.',
  'レンダリング前': 'Before rendering',
  'まだ映像は書き出していません。生成AIへの依頼も、外部への送信もしていません。文言を直してから承認してください。':
    'Nothing has been rendered yet. No AI provider has been contacted and nothing has been sent anywhere. Edit the wording, then approve.',
  '機能の主張そのものは企画で確定済みです。ここで直すのは、見出し・補足・字幕の言い回しです。':
    'What the product claims was settled in the brief. What you change here is how the headlines, supporting lines and captions are worded.',
  'この映像の狙い': 'What this film is for',
  '演出方針': 'Visual direction',
  '見出し': 'Headline',
  '補足': 'Supporting line',
  '字幕': 'Caption',
  '空欄なら見出しを使います': 'Empty means use the headline',
  '編集は制作者の文言として記録されます。': 'Edits are recorded as your wording.',
  '下書きとして保存': 'Save as draft',
  '承認してレンダリング ↗': 'Approve and render ↗',
  '構成を直して、この素材のまま作り直す': 'Reword it and re-render from the same material',
  '収録済みの映像をそのまま使います。再収録も、生成AIへの再依頼も行いません。作り直すと現在の動画・LP・キットは置き換わります。':
    'The existing recording is reused. Nothing is recorded again and no provider is asked again. Re-rendering replaces the current film, page and kit.',
  '投稿済みの内容は変わりません。': 'Anything already sent stays as it was.',
  'この内容で作り直す ↻': 'Re-render with these words ↻',
  '収録した画面の1コマ': 'One frame of what was recorded',
  '構成を保存しました。': 'Storyboard saved.',
  '変更はありません。': 'Nothing changed.',
  '構成を承認しました。レンダリングを開始します。': 'Storyboard approved. Rendering now.',
  '同じ素材のまま、作り直しています。': 'Re-rendering from the same material.',

  // — landing page tab —
  'LPは、映像と一緒に仕上がります。': 'The landing page arrives with the film.',
  '別タブで見る ↗': 'Open in a tab ↗',
  'HTMLを含むキット ↓': 'Kit with the HTML ↓',
  'レスポンシブHTML・CSS・JS / 自動公開は行っていません。': 'Responsive HTML, CSS and JS. Nothing was published automatically.',
  '生成したランディングページ': 'The generated landing page',
  '公開先へ置く': 'Put it where you publish',
  '書き込む内容を確認 ↻': 'Preview what gets written ↻',
  '自分が公開に使っているディレクトリへ、生成した5つのファイルだけをコピーします。ほかのファイルは消しません。アップロードやDNSの設定は行いません。':
    'Copies the five generated files into the directory you publish from. Nothing else there is deleted. Nothing is uploaded and no DNS is touched.',
  'このキャンペーンはまだ保留中です。公開可能にしてから配信してください。':
    'This campaign is still held. Release it before its page goes anywhere.',
  '配信先が未設定です。': 'No deploy target is configured.',
  'に、自分が公開に使っているディレクトリを設定して再起動してください。ホスティングのAPI連携は実装していません。':
    ' to the directory you publish from, then restart. Hosting provider APIs are not implemented.',
  '書き込み先：': 'Writing to: ',
  '新しく置く': 'Adds',
  '置き換える': 'Replaces',
  '変更なし': 'Unchanged',
  '承認は、いま確認したこの内容に対してのみ有効です。': 'This approval covers exactly the files you just reviewed.',
  'この内容で書き出す ↗': 'Write these files ↗',
  '確認しています…': 'Checking…',

  // — distribution —
  '↗ &nbsp; 配信は、最後の承認から。': '↗ \u00a0 Nothing leaves without approval.',
  '投稿先を読み込む ↻': 'Load destinations ↻',
  '実状態を確認 ↻': 'Check what actually happened ↻',
  'Postiz連携あり。投稿原稿・動画・アカウントを確認してから、送信してください。':
    'Postiz is connected. Check the copy, the film and the account before sending.',
  'Postizは未接続です。原稿のコピーと送信データのプレビューは使用できます。実投稿には接続設定が必要です。':
    'Postiz is not connected. You can still edit, copy and dry-run the payload; sending for real needs the connection configured.',
  '予約はPostizに委任します。「受付済み」は各SNSでの公開成功を意味しません。':
    'Scheduling is delegated to Postiz. "Accepted" does not mean a platform published it.',
  '公開可能にする ↗': 'Release for publishing ↗',
  '保留に戻す': 'Hold again',
  'まだ、何も外に出せません。': 'Nothing can leave yet.',
  '映像が完成しても、公開の判断は別の操作です。準備ができたら公開可能にしてください。':
    'Finishing the film is not a decision to publish it. Release the campaign when you are ready.',
  'このキャンペーンは、送信できる状態です。': 'This campaign may be sent.',
  '投稿ごとの承認は、引き続き別に必要です。': 'Each post still needs its own approval.',
  '投稿先 integration ID': 'Destination integration ID',
  'PostizのアカウントID': 'Postiz account ID',
  '予約日時（空欄は今すぐ）': 'Schedule (empty means now)',
  'プラットフォーム設定（JSON）': 'Platform settings (JSON)',
  '原稿をコピー': 'Copy the text',
  '別の切り口にする ↺': 'Try the other hook ↺',
  '内容を確認 ↗': 'Review it ↗',
  '承認待ち': 'Awaiting approval',
  '送信履歴はありません。外部への投稿はまだ行っていません。': 'No sends yet. Nothing has been posted anywhere.',
  '突合する ↗': 'Reconcile ↗',
  '投稿を見る ↗': 'See the post ↗',
  'SNSで公開済み': 'Published',
  'Postizで待機中': 'Queued in Postiz',
  '失敗': 'Failed',
  '見つからない': 'Not found',
  '不明': 'Unknown',
  '原稿をコピーしました。': 'Copied.',
  'ブラウザがコピーを許可していません。原稿を選択してコピーしてください。':
    'The browser refused clipboard access. Select the text and copy it.',
  '切り口を差し替えました。予約時刻をずらして別バージョンとして出せます。':
    'Hook swapped. Schedule it apart from the first to post it as a variant.',
  '公開可能にしました。投稿ごとの承認は引き続き必要です。': 'Released. Each post still needs its own approval.',
  '保留に戻しました。未送信の投稿は送信できません。': 'Held again. Nothing unsent can be sent.',
  '確認できる送信記録がまだありません。': 'There are no sends to check yet.',

  // — approval dialog —
  '届ける前に、もう一度。': 'One more look before it goes.',
  '承認対象 SHA-256': 'SHA-256 of what you are approving',
  '原稿・機能の主張・実際の動画を確認しました。': 'I have read the copy, the claims and the actual film.',
  '映像・音声の利用権を確認しました。': 'I have the rights to this footage and audio.',
  'このアカウントへの公開を許可します。': 'I authorise publishing to this account.',
  '送信データを見る（送信なし）': 'Show the payload (sends nothing)',
  '実投稿は無効です。接続設定・有効な投稿先ID・明示的な実行許可が必要です。':
    'Live publishing is off. It needs the connection configured, a real destination ID, and explicit permission.',
  '3つの確認項目を確認してください。': 'Confirm all three.',
  'Postizが受け付けました。実際の公開結果はPostiz側でも確認してください。':
    'Postiz accepted it. Check Postiz for what the platform actually did.',
  '今すぐ（明示送信した時点）': 'now, at the moment you send',

  // — reconciliation —
  '送信の結果を、目で確かめる。': 'Look at what actually exists.',
  'Postizの記録を確認しています…': 'Reading what Postiz holds…',
  '同じアカウント・同じ書き出しの投稿が見つかりました。該当するものを選んでください。':
    'These posts are on the same account and start with the same text. Pick yours, if one of them is.',
  '送信時のIDと一致する投稿が見つかりました。': 'A post matching the id we recorded was found.',
  'この期間に、該当しそうな投稿は見つかりませんでした。': 'Nothing in this window looks like it.',
  'Postizの投稿ID（手元で確認した場合）': 'Postiz post id, if you found one',
  '例: cmxxxx': 'e.g. cmxxxx',
  'どこで確認したか': 'Where you checked',
  'メモ': 'Note',
  '投稿は作られていない': 'Nothing was created',
  'この投稿として記録する ↗': 'Record it as this post ↗',
  '実在する投稿として記録しました。': 'Recorded as a real post.',
  '未作成として記録しました。承認済みに戻したので、必要なら送信し直せます。':
    'Recorded as never created. It is approved again, so you can deliberately send once more.',

  // — results —
  '数字がないときは、ないと伝えます。': 'When there are no numbers, it says so.',
  'LPの表示': 'Page views',
  'CTAクリック': 'CTA clicks',
  '登録完了': 'Signups',
  'イベント数 / ユニーク訪問者ではありません': 'Event counts, not unique visitors',
  '実際に送信された計測イベント': 'Events actually received',
  '自社バックエンドで確認した登録のみ': 'Only signups your backend confirmed',
  'まだ知らないことは、埋めない。': 'What it does not know, it leaves empty.',
  'まだ判断に必要な実測がありません。': 'There is not enough measured data to conclude anything yet.',
  '実測値を待っています。': 'Waiting for real measurements.',
  '計測接続が設定されています。': 'Measurement is configured.',
  'LP計測は未設定です。PUBLIC_TRACKING_BASEを設定して新しく制作してください。':
    'Page measurement is off. Set PUBLIC_TRACKING_BASE and build a new campaign.',
  'Postizの実測値を取得 ↻': 'Fetch what Postiz measured ↻',

  // — activity —
  'すべての工程に、足あとを。': 'A trace for every step.',
  '何が、どこまで進んだか。': 'What happened, and how far it got.',
  '制作を開始すると記録されます。': 'Entries appear once a build starts.',
  '制作を停止しました。公開は行っていません。': 'The build stopped. Nothing was published.',
  '元の設定で再試行': 'Retry with the original settings',
  '企画を作成するか、内蔵サンプルでローカル制作をお試しください。外部への投稿は行いません。':
    'Write a brief, or run the bundled sample locally. Nothing is posted anywhere.',
  '企画をつくる ↗': 'Write a brief ↗',

  // — create dialog —
  '何を、届けますか。': 'What are you putting out?',
  'プロダクト名': 'Product name',
  '誰に届けたい？': 'Who is it for?',
  'いちばん伝えたいこと': 'The one thing to say',
  'プロダクトの説明': 'What it does',
  'どんな場面で、何が変わるのか。': 'In what moment does it change something?',
  '公開先URL（未公開なら空欄）': 'Public URL (leave empty if unreleased)',
  '紹介してよい機能と根拠': 'Features you may claim, and your evidence',
  '1行につき「機能名 | 説明 | 動作確認・仕様の根拠」': 'One per line: name | description | how you verified it',
  '音声でタスクを追加 | 話しかけるとタスク一覧へ追加できます | v0.1の実機テストで確認':
    'Add tasks by voice | speak and it lands in the list | verified on device in v0.1',
  'アクセントカラー': 'Accent colour',
  '制作言語': 'Output language',
  '日本語': 'Japanese',
  '記載した機能が実装済みであることを確認しました。': 'I confirm the features listed above are implemented.',
  '実際の操作を、見せる。': 'Show it actually being used.',
  '実プロダクトの操作映像と、AIによるコンセプト映像は別の素材として扱います。':
    'Footage of your real product and AI-generated concept video are kept as separate material.',
  '操作映像の入力': 'Where the footage comes from',
  'まずは紹介アニメーションをつくる': 'Motion graphics for now',
  'ステージングURLを自動収録する': 'Drive and record a staging URL',
  '操作動画をアップロード / 画面収録する': 'Upload a recording, or record the screen',
  '収録URL': 'URL to record',
  'CAPTURE_ALLOWED_ORIGINSへの明示追加が必要です。外部サイトへの変更リクエストは既定で停止します。':
    'The origin must be listed in CAPTURE_ALLOWED_ORIGINS. Requests that would change the site are blocked by default.',
  '操作手順（JSON配列。JavaScriptは実行しません）': 'Steps as a JSON array (no JavaScript is executed)',
  '画面から隠すCSSセレクター（1行ずつ）': 'CSS selectors to hide, one per line',
  'テスト環境・テストデータであり、操作を許可します。': 'This is a test environment with test data, and I authorise driving it.',
  'このテスト環境への送信・変更リクエストも許可します。': 'I also allow requests that write to this test environment.',
  '操作動画（最大200MB / 5分）': 'Recording (up to 200 MB / 5 minutes)',
  '● &nbsp; このブラウザから画面収録': '● \u00a0 Record the screen from this browser',
  '● もう一度収録する': '● Record again',
  '■ 収録を停止': '■ Stop recording',
  '表示される共有ダイアログで対象を選択します。': 'Choose what to share in the dialog your browser shows.',
  '画面収録はユーザー操作で開始・停止します。録画元の機密情報は事前に隠してください。':
    'Recording starts and stops on your action. Hide anything confidential before you begin.',
  '画面収録中です。最大約5分で自動停止します。': 'Recording. It stops on its own after about five minutes.',
  '操作イベント（任意・JSON配列）': 'Event track (optional, JSON array)',
  '取り込んだ映像にはカーソル情報がありません。指定すると、収録時と同じ寄りと画面上のラベルが付きます。':
    'Imported footage carries no cursor data. Supply a track and it gets the same camera work and on-screen labels as a live capture.',
  '使い始める位置（秒）': 'Start at (seconds)',
  '0なら収録の先頭から': '0 means the beginning',
  '使う長さ（秒）': 'Use this much (seconds)',
  '0なら最大20秒まで': '0 means up to 20 seconds',
  '音楽（任意）': 'Music (optional)',
  'ナレーションがある場合は自動的に下げます': 'Held under narration automatically',
  'ナレーション（任意）': 'Narration (optional)',
  '読み上げ音声の生成は行いません': 'No speech is generated',
  'アップロード・収録する映像や音声を使用する権利があります。': 'I have the rights to the footage and audio I upload or record.',
  'レンダリングの前に、構成と収録内容を確認する。': 'Stop before rendering so I can read the storyboard and the capture.',
  '届ける場所と、その先。': 'Where it goes, and what happens next.',
  '目的': 'Goal',
  '利用登録': 'Signups',
  'デモ体験': 'Demos',
  'GitHubで使ってもらう': 'GitHub adoption',
  '生成AI・制作設定': 'Generative AI and production settings',
  'コンセプト映像': 'Concept footage',
  'ローカル（生成AI料金なし）': 'Local (no AI fees)',
  'fal（BYOK・有料）': 'fal (your key, paid)',
  'ComfyUI（自分の環境）': 'ComfyUI (your own server)',
  '画質': 'Quality',
  'ビジュアル方向': 'Visual direction',
  'Editorial ／ 余白と紙の質感、静かな書体': 'Editorial — space, paper, quiet type',
  'Editorial ／ 余白と紙の質感': 'Editorial — space and paper',
  'Spotlight ／ 暗がりに、製品だけが光る': 'Spotlight — a dark room, the product lit',
  'Grid ／ 方眼と小さな見出し、硬い輪郭': 'Grid — a measured grid and hard edges',
  'Grid ／ 方眼と小さな見出し': 'Grid — a measured grid, small capitals',
  'Provider入力 JSON（モデルの公式スキーマに合わせる）': 'Provider input JSON (match the model’s documented schema)',
  '今回の映像生成見積り（USD）': 'Your cost estimate for this generation (USD)',
  '設定したLLMで演出・映像プロンプトを企画する。': 'Use the configured LLM to write the direction and the video prompt.',
  '製品名・説明・承認済み機能・生成指示を、選択した外部Providerへ送信することを許可します。':
    'I allow the product name, description, approved features and generation instructions to be sent to the provider I chose.',
  'APIキーはサーバーの環境変数で設定します。料金上限は入力見積りベースであり、Providerの実請求額を保証しません。':
    'API keys live in the server environment. The budget is based on the estimates you type; it is not the provider’s bill.',
  '公開・SNS投稿は行いません。': 'Nothing is published or posted.',
  '制作をはじめる ↗': 'Start producing ↗',
  '使用する映像・音声の権利を確認してください。': 'Confirm you have the rights to the footage and audio.',
  '操作動画を選択するか、画面を収録してください。': 'Choose a recording, or record the screen.',
  '収録URLとテスト環境の確認が必要です。': 'A URL and the test-environment confirmation are both required.',
  '選択した外部Providerへの送信許可が必要です。': 'Sending to the provider you chose needs your permission.',
  'SNSを1つ以上選択してください。': 'Choose at least one channel.',
  '機能は「機能名 | 説明 | 根拠」の3項目で入力してください。': 'Each feature needs three parts: name | description | evidence.',
  '画面収録を停止してから制作してください。': 'Stop the recording before producing.',
  'ひとりで、いいプロダクトをつくる人': 'people who build good things alone',
  '仕事は静かに、前へ進む。': 'Work moves quietly forward.',

  // — settings / connection wizard —
  'つながる。でも、縛られない。': 'Connected, never captive.',
  'キーはサーバーの .env で設定して再起動します。ブラウザにAPIキーは保存しません。':
    'Keys go in the server’s .env and take effect on restart. No API key is stored in the browser.',
  '1. PostizにSNSを接続する': '1. Connect your accounts in Postiz',
  'SNSのOAuthはPostiz側で行います。Launchloomは、Postizが接続済みのアカウントにだけ投稿します。':
    'Social OAuth happens in Postiz. Launchloom only ever posts to accounts Postiz already holds.',
  '2. 接続を確かめる': '2. Check the connection',
  '「投稿先を読み込む」で、Postizが持っているアカウントを取得します。':
    '"Load destinations" fetches the accounts Postiz has.',
  '3. 実投稿を許可する': '3. Allow live publishing',
  '既定では送信しません。': 'Nothing is sent by default.',
  'にして再起動すると、承認した投稿だけ送信できます。': ' and restart, and approved posts can be sent.',
  '4. キャンペーンを公開可能にする': '4. Release the campaign',
  '完成とは別の判断です。配信タブで公開可能にしてから、投稿ごとに承認します。':
    'A separate decision from finishing it. Release it in the distribution tab, then approve each post.',
  'ローカル制作': 'Local production',
  'fal 映像生成': 'fal video generation',
  '企画LLM': 'Planning LLM',
  '外部投稿の実行許可': 'Live publishing allowed',
  'LP配信先': 'Page deploy target',
  'LP計測': 'Page measurement',
  '有効': 'On',
  '未設定 / 無効': 'Not set / off',
  '無料のローカル制作は、APIキーなしで動作します。非公開データを含む本番環境の収録は避けてください。':
    'Producing locally is free and needs no API key. Do not record production environments that contain private data.',
  'Postizの環境変数を設定して再起動してください。': 'Set the Postiz environment variables and restart.',

  // — progress log lines —
  '企画と根拠を整理しています。未承認の機能は宣伝に使いません。':
    'Sorting the brief and its evidence. Unapproved features are never advertised.',
  '同じメッセージ・配色・CTAで、レスポンシブLPを作っています。':
    'Building a responsive landing page with the same message, palette and call to action.',
  '操作映像を準備しています。収録と生成映像の出どころは区別して保存します。':
    'Preparing the footage. Recorded and generated material are stored as separate sources.',
  '設定した生成映像Providerへ接続します。操作画面の証拠としては使用しません。':
    'Contacting the configured video provider. Its output is never used as evidence of a feature.',
  '横長と縦長を別レイアウトで編集・書き出ししています。': 'Cutting and exporting landscape and vertical as separate layouts.',
  'LPに操作動画を配置し、SNS原稿と配布パッケージを作っています。':
    'Placing the film on the page and writing the drafts and the kit.',
  '出力の解像度・動画形式・欠損・原稿の根拠を検査しています。':
    'Checking resolution, container, missing files and the evidence behind the copy.',
  '制作パッケージができました。外部への公開・投稿はまだ行っていません。':
    'The kit is ready. Nothing has been published or posted.',
  '構成と収録内容を確認してください。承認するまでレンダリングも生成AIも実行しません。':
    'Read the storyboard and the capture. Nothing renders and no provider is contacted until you approve.',
  '承認済みの構成で制作します。文言は上書きしません。': 'Producing from the approved storyboard. Your wording is not overwritten.',
  '構成を編集しました（文言は制作者によるもの）。': 'Storyboard edited (the wording is the operator’s).',
  'この素材のまま、構成を作り直します。再収録と生成AIへの再依頼は行いません。':
    'Re-composing from the same material. Nothing is recorded again and no provider is asked again.',
  'キャンペーンを公開可能にしました。個々の投稿は、引き続き投稿ごとの承認が必要です。':
    'The campaign may now be published. Each post still needs its own approval.',
  '公開を保留にしました。未送信の投稿は送信できません。': 'Publishing is held. Nothing unsent can be sent.',
  '字幕とモーショングラフィックスのみ。音声トラック未設定です。': 'Captions and motion graphics only. No audio track was supplied.',
  'ナレーションの下で、音楽の音量を下げています。': 'The music is held under the narration.',
  '公開先の product_url が未設定です。': 'No public product_url is set.',
  'サンプルアプリの映像です。ユーザーの実プロダクトは未収録です。':
    'This is footage of the sample app. Your own product has not been recorded.',

  // — placeholders and examples —
  '[{"action":"click","selector":"#try-demo","label":"試してみる","milliseconds":1500}]':
    '[{"action":"click","selector":"#try-demo","label":"Try it","milliseconds":1500}]',
  '[{"time":1.4,"action":"click","x":0.42,"y":0.33,"label":"その場で書き留める。"}]':
    '[{"time":1.4,"action":"click","x":0.42,"y":0.33,"label":"Write it down on the spot."}]',
  '承認して投稿': 'Approve and post',
  '承認して予約': 'Approve and schedule',
  'SNSインプレッション：未取得。未取得の値は推計で補いません。':
    'Social impressions: not retrieved. Nothing unavailable is filled in with an estimate.',
  '同じSNSへは{gap}分以上あけ、1日{max}件までにしています。':
    'At least {gap} minutes between posts on one channel, and at most {max} a day.',
  '動画': 'Film',
  '投稿': 'Post',
  '予約': 'Schedule',
  'なし': 'none',

  'HD / 1280×720・720×1280': 'HD — 1280×720 and 720×1280',
  'Draft / 960×540・540×960': 'Draft — 960×540 and 540×960',
  '投稿先': 'Destination',
  '実行': 'When',
  '改訂': 'revision',
  '件の投稿先を取得しました。': ' destinations loaded.',
  '件の投稿先が見つかりました：': ' destinations found: ',
  '件を確認しました。': ' checked.',
  '件はPostizに見つかりません。': ' are not in Postiz.',
  'このディレクトリの他のファイル（': 'Everything else in that directory (',
  '）はそのまま残ります。': ') is left alone.',
  ' ほか': ' and more',
  'のPostizの記録です。': ' — the Postiz records for this window.',
};

const TABLES = { en: EN };
const CJK = /[぀-ヿ㐀-鿿]/;
const ATTRIBUTES = ['placeholder', 'title', 'alt', 'aria-label'];

export function preferredLanguage() {
  const stored = (() => { try { return localStorage.getItem('launchloom_language'); } catch { return null; } })();
  if (stored && (stored === 'ja' || TABLES[stored])) return stored;
  return (navigator.language || 'ja').toLowerCase().startsWith('ja') ? 'ja' : 'en';
}

export function setLanguage(language) {
  try { localStorage.setItem('launchloom_language', language); } catch { /* private mode */ }
  location.reload();
}

// Replaces whole text nodes only. A partial match would corrupt anything the
// operator typed, and translated text no longer matches, so this is idempotent.
const normalise = (text) => text.replace(/&nbsp;/g, ' ').replace(/\u00a0/g, ' ').trim();

// Keys are written the way the markup writes them, including &nbsp;. The DOM
// hands us a real non-breaking space, so both sides are normalised once here.
const LOOKUPS = Object.fromEntries(Object.entries(TABLES).map(
  ([code, table]) => [code, Object.fromEntries(Object.entries(table).map(([key, value]) => [normalise(key), value]))]));

// Look up a single string directly, for the few places where markup and values
// are interpolated into one text node.
export function t(japanese, language = preferredLanguage()) {
  const table = LOOKUPS[language];
  return (table && table[normalise(japanese)]) ?? japanese;
}

export function translate(root = document.body, language = preferredLanguage()) {
  const table = LOOKUPS[language];
  if (!table || !root) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (CJK.test(node.nodeValue)) nodes.push(node);
  }
  for (const node of nodes) {
    const text = normalise(node.nodeValue);
    const replacement = table[text];
    if (replacement !== undefined) node.nodeValue = replacement;
  }
  const elements = root.querySelectorAll ? root.querySelectorAll('*') : [];
  for (const element of elements) {
    for (const attribute of ATTRIBUTES) {
      const value = element.getAttribute && element.getAttribute(attribute);
      if (value && CJK.test(value) && table[normalise(value)] !== undefined) {
        element.setAttribute(attribute, table[normalise(value)]);
      }
    }
  }
  if (root === document.body && table[document.title]) document.title = table[document.title];
}

// Everything the studio renders passes through here, including dialogs it fills
// in later, without any render path needing to know translation exists.
export function watch(language = preferredLanguage()) {
  if (language === 'ja' || !LOOKUPS[language]) return;
  document.documentElement.lang = language;
  translate(document.body, language);
  new MutationObserver((records) => {
    for (const record of records) {
      for (const added of record.addedNodes) {
        if (added.nodeType === 1) translate(added, language);
        else if (added.nodeType === 3 && CJK.test(added.nodeValue)) {
          const replacement = LOOKUPS[language][normalise(added.nodeValue)];
          if (replacement !== undefined) added.nodeValue = replacement;
        }
      }
      if (record.type === 'characterData' && CJK.test(record.target.nodeValue || '')) {
        const replacement = LOOKUPS[language][normalise(record.target.nodeValue)];
        if (replacement !== undefined) record.target.nodeValue = replacement;
      }
    }
  }).observe(document.body, { childList: true, subtree: true, characterData: true });
}
