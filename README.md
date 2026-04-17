# Backstage Realtime Ranking Scraper

Backstageから**全エージェンシークリエイター768名の今月累計ダイヤ**を取得し、ランキングJSONを出力。

## 初回セットアップ（Macで1回だけ）

```bash
cd /Users/k/Documents/TikTok_月次データ/realtime_scraper
pip3 install --user -r requirements.txt
playwright install chromium
python3 login.py   # ブラウザ開く → Backstageにログイン → Enter
```

`storage_state.json` が生成されます（Cookie含む、Git commitしないこと）。

## 動作確認

```bash
python3 scrape.py              # headlessで実行
HEADLESS=0 python3 scrape.py   # ブラウザ表示（デバッグ用）
```

成功すると:
- `ranking_realtime_internal.json` （社内用、全クリエイター）
- `ranking_realtime_livers.json` （ライバー用、Top20）

が出力されます。

## データフロー

```
Backstage → Playwright (セッション流用) → API 8ページfetch
         → records整形 → 2種のJSON出力
```

## GitHub Actions版（自動実行）

`storage_state.json` の中身をbase64エンコードしてGitHubシークレット `SESSION_STATE_B64` に登録。
ワークフローが5分ごとに実行、JSONをGitHub Pagesにpush、Vercelサイトがそれをfetch。
