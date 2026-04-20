/**
 * Cloudflare Worker: triggers GitHub Actions workflow_dispatch on a reliable cron.
 *
 * Triggers configured in wrangler.toml (every 90 minutes, split into 2 crons because
 * cron minute field is 0-59).
 *
 * Manual test:
 *   curl "https://<worker>.workers.dev/?key=<TRIGGER_KEY>"
 *
 * Secrets (set via `wrangler secret put`):
 *   GITHUB_PAT   — Fine-grained PAT, Actions:Read-and-write on tiktok-ranking-data
 *   TRIGGER_KEY  — shared secret for manual ?key=… trigger
 */

const GITHUB_OWNER = "katsupiano";
const GITHUB_REPO = "tiktok-ranking-data";
const WORKFLOW_FILE = "scrape.yml";
const WORKFLOW_REF = "main";

const USER_AGENT = "tiktok-ranking-cron-worker";

async function dispatchWorkflow(env, reason) {
  const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_PAT}`,
      Accept: "application/vnd.github+json",
      "User-Agent": USER_AGENT,
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: WORKFLOW_REF }),
  });

  if (resp.status !== 204) {
    const body = await resp.text();
    console.error(
      `[${reason}] dispatch failed: HTTP ${resp.status} — ${body.slice(0, 500)}`,
    );
    return { ok: false, status: resp.status, body };
  }
  console.log(`[${reason}] dispatch OK (204)`);
  return { ok: true, status: 204 };
}

export default {
  /**
   * Scheduled cron handler — fires at times defined in wrangler.toml triggers.crons.
   */
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatchWorkflow(env, `cron:${event.cron}`));
  },

  /**
   * HTTP handler — manual trigger via `/?key=<TRIGGER_KEY>`.
   */
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const key = url.searchParams.get("key");

    if (url.pathname === "/health") {
      return new Response("ok", { status: 200 });
    }

    if (!key || key !== env.TRIGGER_KEY) {
      return new Response("Forbidden", { status: 403 });
    }

    const result = await dispatchWorkflow(env, "manual");
    if (!result.ok) {
      return new Response(
        `GitHub dispatch failed: ${result.status}\n${result.body || ""}`,
        { status: 502 },
      );
    }
    return new Response("Dispatched", { status: 204 });
  },
};
