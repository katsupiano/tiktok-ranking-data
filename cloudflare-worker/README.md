# Cloudflare Worker: TikTok Ranking Cron

GHA cronの発火遅延・スキップを回避するため、Cloudflare Workers Cron から
GitHub Actions `workflow_dispatch` を叩いて確実に発火させる。

## 初回セットアップ

### 1. PAT発行（GitHub）

Fine-grained PAT: https://github.com/settings/personal-access-tokens/new
- Token name: `cloudflare-worker-dispatch`
- Resource owner: `katsupiano`
- Repository access: Only select repositories → **`tiktok-ranking-data`**
- Repository permissions:
  - **Actions: Read and write** （`workflow_dispatch` 必須）
  - Metadata: Read-only（自動）
- Expiration: 1年（カレンダーにリマインダー登録推奨）

発行された `github_pat_...` をコピー。

### 2. TRIGGER_KEY生成

```bash
openssl rand -hex 32
```

出力された64文字をコピー。

### 3. Cloudflareログイン & デプロイ

```bash
cd cloudflare-worker
npx wrangler login                     # ブラウザでCloudflareログイン
npx wrangler secret put GITHUB_PAT     # 1. の値を貼り付け
npx wrangler secret put TRIGGER_KEY    # 2. の値を貼り付け
npx wrangler deploy
```

### 4. 手動テスト

```bash
curl -i "https://tiktok-ranking-cron.<your-subdomain>.workers.dev/?key=<TRIGGER_KEY>"
```

`HTTP/2 204` が返ればOK。GitHub Actionsタブで `workflow_dispatch` 起動確認。

### 5. ヘルスチェック（キー不要）

```bash
curl "https://tiktok-ranking-cron.<your-subdomain>.workers.dev/health"
# → "ok"
```

## Cron設定

90分間隔（1日16回）:

```
0  0,3,6,9,12,15,18,21 * * *  UTC  → JST  09:00, 12:00, 15:00, 18:00, 21:00, 00:00, 03:00, 06:00
30 1,4,7,10,13,16,19,22 * * * UTC  → JST  10:30, 13:30, 16:30, 19:30, 22:30, 01:30, 04:30, 07:30
```

## 既存GHA cronとの関係

冗長化のため `.github/workflows/scrape.yml` のcronもしばらく残す。
`concurrency: group: scrape, cancel-in-progress: false` で重複起動は自動キューイング。
Workers側が1週間安定運用できたらGHA cronを間引く判断をする。

## ログ・監視

- リアルタイム: `npx wrangler tail`
- ダッシュボード: https://dash.cloudflare.com → Workers → tiktok-ranking-cron → Logs

## シークレット更新

PATが期限切れになったら:

```bash
npx wrangler secret put GITHUB_PAT
# 新PATを貼り付け
```

再デプロイ不要、即反映。
