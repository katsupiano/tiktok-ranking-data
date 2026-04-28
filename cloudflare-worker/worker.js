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
// Monthly stays in private repo (internal data); event moved to public repo (Actions unlimited).
const REPO_MONTHLY = "tiktok-ranking-data";
const REPO_EVENT = "tiktok-event-scraper";
const WORKFLOW_MONTHLY = "scrape.yml";
const WORKFLOW_EVENT = "scrape-event.yml";
const WORKFLOW_REF = "main";

const USER_AGENT = "tiktok-ranking-cron-worker";

// Map cron → (repo, workflow). Any cron whose minute field contains "*/10"
// dispatches the 10-minute event scraper in the public event repo; everything else
// dispatches the 90-minute monthly scraper in the private monthly repo.
function targetForCron(cron) {
  if (cron && cron.startsWith("*/10 ")) return { repo: REPO_EVENT, workflow: WORKFLOW_EVENT };
  return { repo: REPO_MONTHLY, workflow: WORKFLOW_MONTHLY };
}

async function dispatchWorkflow(env, repo, workflowFile, reason) {
  const url = `https://api.github.com/repos/${GITHUB_OWNER}/${repo}/actions/workflows/${workflowFile}/dispatches`;
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
      `[${reason}] ${repo}/${workflowFile} dispatch failed: HTTP ${resp.status} — ${body.slice(0, 500)}`,
    );
    return { ok: false, status: resp.status, body };
  }
  console.log(`[${reason}] ${repo}/${workflowFile} dispatch OK (204)`);
  return { ok: true, status: 204 };
}

export default {
  async scheduled(event, env, ctx) {
    const { repo, workflow } = targetForCron(event.cron);
    ctx.waitUntil(dispatchWorkflow(env, repo, workflow, `cron:${event.cron}`));
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
    const target = wf === "event"
      ? { repo: REPO_EVENT, workflow: WORKFLOW_EVENT }
      : { repo: REPO_MONTHLY, workflow: WORKFLOW_MONTHLY };

    const result = await dispatchWorkflow(env, target.repo, target.workflow, "manual");
    if (!result.ok) {
      return new Response(
        `GitHub dispatch failed: ${result.status}\n${result.body || ""}`,
        { status: 502 },
      );
    }
    return new Response(`Dispatched ${target.repo}/${target.workflow}\n`, { status: 200 });
  },
};
