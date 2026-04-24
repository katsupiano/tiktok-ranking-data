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
const WORKFLOW_MONTHLY = "scrape.yml";
const WORKFLOW_EVENT = "scrape-event.yml";
const WORKFLOW_REF = "main";

const USER_AGENT = "tiktok-ranking-cron-worker";

// Map cron → workflow file. Any cron whose minute field contains "*/10"
// dispatches the 10-minute event scraper; everything else dispatches the
// 90-minute monthly scraper.
function workflowForCron(cron) {
  if (cron && cron.startsWith("*/10 ")) return WORKFLOW_EVENT;
  return WORKFLOW_MONTHLY;
}

async function dispatchWorkflow(env, workflowFile, reason) {
  const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${workflowFile}/dispatches`;
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
      `[${reason}] ${workflowFile} dispatch failed: HTTP ${resp.status} — ${body.slice(0, 500)}`,
    );
    return { ok: false, status: resp.status, body };
  }
  console.log(`[${reason}] ${workflowFile} dispatch OK (204)`);
  return { ok: true, status: 204 };
}

export default {
  /**
   * Scheduled cron handler — fires at times defined in wrangler.toml triggers.crons.
   */
  async scheduled(event, env, ctx) {
    const workflowFile = workflowForCron(event.cron);
    ctx.waitUntil(dispatchWorkflow(env, workflowFile, `cron:${event.cron}`));
  },

  /**
   * HTTP handler — manual trigger via `/?key=<TRIGGER_KEY>[&wf=event|monthly]`.
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

    const wf = url.searchParams.get("wf");
    const workflowFile = wf === "event" ? WORKFLOW_EVENT : WORKFLOW_MONTHLY;

    const result = await dispatchWorkflow(env, workflowFile, "manual");
    if (!result.ok) {
      return new Response(
        `GitHub dispatch failed: ${result.status}\n${result.body || ""}`,
        { status: 502 },
      );
    }
    return new Response(`Dispatched ${workflowFile}\n`, { status: 200 });
  },
};
