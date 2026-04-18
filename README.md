# Backstage Realtime Ranking Scraper

Backstageから全エージェンシークリエイター（アルファ+ユリシス）の今月累計ダイヤを取得し、
マンスリーランキングJSONを2系統に出力する。

## 2リポ構成

このリポ（private）で全データを生成しつつ、配信用は別のpublicリポに分離している。
GitHub Free プランではprivate repoのPagesが使えないため。

```
tiktok-ranking-data   (private) … コード + 社内用internal JSON
  └─ 90分ごとに scrape.py 実行
     ├─ docs/ranking_realtime_internal.json        ← 全クリエイター、社内閲覧のみ
     └─ docs/ranking_realtime_livers.json          ← Top20、外部公開

tiktok-ranking-livers-feed  (public) … livers JSON のみミラー
  └─ GitHub Pages で配信 → Vercelサイトが fetch
```

## 初回セットアップ（ローカルMacで1回だけ）

```bash
pip3 install --user -r requirements.txt
playwright install chromium
python3 login.py           # alpha（bcode）でログイン
python3 login_ulysses.py   # ユリシス（grove）でログイン（あれば）
python3 scrape.py          # 動作確認
```

## 実行頻度

- **90分ごと**（1日16回）
- cron: `0 0,3,6,9,12,15,18,21 * * *` と `30 1,4,7,10,13,16,19,22 * * *` の2本立て
- Actions使用時間見込み: 約3分/回 × 16回/日 × 30日 ≈ **1,440分/月**（無料枠2,000分内）

## 出力ファイル

```
docs/ranking_realtime_internal.json        ← 現在月（上書き更新）
docs/ranking_realtime_internal_YYYYMM.json ← 月次スナップショット
docs/ranking_realtime_livers.json
docs/ranking_realtime_livers_YYYYMM.json
```

月が変わると自動的に新しい `_YYYYMM.json` が生成され、過去月のアーカイブは凍結される。

## GitHub Secrets

| 名前 | 用途 |
|---|---|
| `SESSION_STATE_B64` | alpha（bcode）セッション、gzip+base64 |
| `SESSION_STATE_ULYSSES_B64` | ユリシスセッション、gzip+base64 |
| `PUBLISH_PAT` | 配信用publicリポへpushするFine-grained PAT |

セッション更新時は `python3 encode_session.py alpha` または `ulysses` を実行し、
出力を各Secretに貼り直す。

## Vercel側の内部JSON取得

social dashboardはprivate repoにあるinternal JSONをVercel Serverless Function
(`api/internal.js`) 経由で取得している（Basic認証＋GitHub Contents API proxy）。
Vercel env vars: `BASIC_AUTH_USER`, `BASIC_AUTH_PASSWORD`, `GH_INTERNAL_TOKEN`。
