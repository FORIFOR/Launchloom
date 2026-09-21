# 5製品の制作パイプライン検証 — 2026-09-13

Genie、AI Meeting、Oathra、AISecure、Agent Teamの既存動作記録をLaunchloomの実パイプラインへ投入し、**10動画・5LP・20投稿原稿**を生成しました。各製品を今回新たに10回操作した証拠や、SNSへ公開した実績ではありません。

## 成果物と条件

- 横1920×1080 / 縦1080×1920、H.264、30fps。尺29.6〜68.7秒。AISecureのみ30秒の目標を0.4秒下回ります。
- 元録画を途中で打ち切らず、元の再生速度を保持。音声のある4素材は元音声を残し、冒頭3秒の追加に合わせて3秒遅らせています。Agent Team元録画には音声がありません。
- 初稿では24秒への切り詰めと音声欠落が見つかり、上記構成へ修正して再生成しました。
- 字幕ファイルはシーン見出しです。全発話を逐語的に字幕化したものではありません。
- X / LinkedIn / YouTube / Instagram向けの原稿とUTM付きURL。すべてdraft、未投稿。個人アカウントへの投稿なし。
- 画面素材は実UI録画ですが、Oathraはシミュレーター、AI Meetingは合成入力、AISecureは合成ログ、Agent Teamはpartial runのリプレイです。素材内・紹介文の条件を維持します。

[集計](evidence/portfolio-20260913.json)と[メディア検査](evidence/portfolio-media-20260913.json)に素材hash・尺・出力条件を記録。今回の生成物は端末のDownloadsに保存しています。大きな動画を証拠なしに成功デモと呼んだり、既存サイトへ自動で置き換えたりしていません。

Codex内ブラウザでも5LPを390×844と1280×900で開き、横方向のはみ出しなし、各動画の読み込みを確認しました。Agent Teamの34.8秒動画はブラウザ上で終端まで再生、media errorなし。[画面と記録](evidence/portfolio-browser-20260913/checks.json)。スマートフォン実機やSafari/Firefoxでの確認とは区別します。

## 再現

このリポジトリと他5製品のチェックアウト/録画が同じProjectsディレクトリにある場合：

```sh
.venv/bin/python scripts/build-portfolio-kits.py /tmp/launchloom-five-products-new /path/to/Projects
.venv/bin/python scripts/verify-portfolio-kits.py /tmp/launchloom-five-products-new
.venv/bin/python -m pytest -q
```

素材がなければ開始時に失敗し、架空の画面を生成して代用しません。レビューで停止した計画を確認済みの素材・claimsに基づいて承認し、書き出します。有料生成・公開・トラッキングサービスを無効化しており、今回の外部API料金は0 USD（機器・電力・既存素材制作費は除外）。

## Claimsと残件

500件の合成Briefを用いた整合性検査を含む **635テスト合格**。これは全ての実プロダクトの事実確認やLLM幻覚率の測定ではありません。検査を壊した場合に通ってしまわないことは既存の負例テストで確認しています。

1080p化は小さな元映像の文字を復元しません。アップロード録画にはcursor metadataがなく、動き・zoom・日本語改行・モバイル実機可読性には映像ごとの目視確認が必要です。Safari/Firefox/モバイル実機、Lighthouse、LCP/CLS、全発話字幕、ブランド別演出の最終評価は未完了です。自動デコード合格を映像の芸術的品質や拡散力の合格に転用しません。

L1の制作能力を示す材料として利用可能。有償PoCではブランド素材と使用権・レビュー担当・納品条件を確定し、L3のマルチユーザー/ホスティング/定期公開/運用SLAは別途検証します。Apache-2.0。素材・フォント・BGMの権利は個別です。
