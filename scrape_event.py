"""
Backstage rank-multistage event scraper (for NEW STAR CUP and similar).

Strategy:
1. Load saved session (storage_state.json) — alpha only (events are typically single-agency)
2. Open rank-multistage-activity-analytics page
3. Capture ranklist/info (event meta + ComponentIDs)
4. Click ステージ tab → agency_component_host_list fires
5. Change page size to 100 and paginate
6. Merge responses → JSON

Output: OUT_DIR/<eventSlug>.json and archive of current stage.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright

BASE = Path(__file__).parent
OUT_DIR = Path(os.environ.get("OUTPUT_DIR", BASE))
STORAGE = BASE / "storage_state.json"

JST = timezone(timedelta(hours=9))

EVENT_URL_TMPL = (
    "https://live-backstage.tiktok.com/portal/tools/activity/"
    "rank-multistage-activity-analytics?activityId={aid}&entryFrom=revenue_activity_page"
)
API_HOST_LIST = "ranklist/agency_component_host_list"
API_INFO = "ranklist/info"
API_METRICS = "review/activity_metrics"

# MetricsKey meanings (from metrics_config inspection):
#  102 = total diamonds earned in event (scope-wide)
METRIC_TOTAL_DIAMONDS = 102


def jst_iso(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), JST).isoformat(timespec="seconds")


def pick_current_component(info: dict) -> Tuple[Optional[str], Optional[dict]]:
    """From ranklist/info, pick the stage currently in progress (or the next upcoming).
    The leaf components (ComponentType=3) are the per-stage leaderboards.
    """
    ag = info.get("AgencyActivity") or {}
    parents = ag.get("ActivityComponentList") or []
    now = int(datetime.now(JST).timestamp())
    leaves = []
    for parent in parents:
        for leaf in parent.get("ActivityComponentList") or []:
            leaves.append(leaf)
    if not leaves:
        return None, None
    leaves.sort(key=lambda c: int(c.get("StartTime", 0) or 0))
    for leaf in leaves:
        s = int(leaf.get("StartTime", 0) or 0)
        e = int(leaf.get("EndTime", 0) or 0)
        if s <= now <= e:
            return leaf.get("ComponentID"), leaf
    # Fall back to the latest one that ended, or the next upcoming
    future = [l for l in leaves if int(l.get("StartTime", 0) or 0) > now]
    if future:
        return future[0].get("ComponentID"), future[0]
    return leaves[-1].get("ComponentID"), leaves[-1]


def scrape(activity_id: str, headless: bool = True) -> dict:
    captures: Dict[Tuple[str, int], dict] = {}  # (ComponentID, Offset) → response
    info_body: Optional[dict] = None
    metrics_body: Optional[dict] = None
    component_total: Dict[str, int] = {}

    def on_response(resp):
        nonlocal info_body, metrics_body
        url = resp.url
        try:
            if API_INFO in url and resp.status == 200:
                try:
                    info_body = resp.json()
                except Exception:
                    pass
                return
            if API_METRICS in url and resp.status == 200:
                try:
                    metrics_body = resp.json()
                except Exception:
                    pass
                return
            if API_HOST_LIST in url and resp.status == 200:
                qs = parse_qs(urlparse(url).query)
                cid = (qs.get("ComponentID") or [""])[0]
                offset = int((qs.get("Offset") or ["0"])[0])
                try:
                    data = resp.json()
                except Exception:
                    return
                if (data.get("BaseResp") or {}).get("StatusCode") != 0:
                    return
                captures[(cid, offset)] = data
                component_total[cid] = int(data.get("Total", 0) or 0)
                print(f"[capture] cid={cid} off={offset} total={data.get('Total')} rows={len(data.get('RecordList') or [])}")
        except Exception as e:
            print(f"[on_response err] {e}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(STORAGE), locale="ja-JP", viewport={"width": 1600, "height": 1000})
        page = context.new_page()
        page.on("response", on_response)

        url = EVENT_URL_TMPL.format(aid=activity_id)
        print(f"[nav] {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        time.sleep(5)

        # Click ステージ tab and wait for the first host_list response
        try:
            with page.expect_response(
                lambda r: API_HOST_LIST in r.url and r.status == 200,
                timeout=20000,
            ):
                page.get_by_role("tab", name="ステージ").click(timeout=10000)
        except Exception as e:
            print(f"[ui] stage tab click/wait err: {e}")

        # Pick current stage's ComponentID from info_body (fires on page load)
        cid, component_meta = (None, None)
        if info_body:
            cid, component_meta = pick_current_component(info_body)
        print(f"[stage] currentComponentID={cid}")

        # Give response handler a tick to finish parsing
        page.wait_for_timeout(500)
        total = component_total.get(cid, 0) if cid else 0
        print(f"[stage] total={total}")

        # Max page size for this API is 40
        PAGE_SIZE = 40
        if cid and total > 10:
            try:
                print(f"[ui] set page size to {PAGE_SIZE}")
                with page.expect_response(
                    lambda r: API_HOST_LIST in r.url and f"Limit={PAGE_SIZE}" in r.url and r.status == 200,
                    timeout=20000,
                ):
                    page.locator(".semi-page-switch .semi-select").first.click(timeout=10000)
                    page.wait_for_timeout(600)
                    page.get_by_role("option", name=f"1ページあたりのアイテム数：{PAGE_SIZE}").click(timeout=8000)
            except Exception as e:
                print(f"[ui] page-size change err: {e}")

            expected_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
            for page_num in range(2, expected_pages + 1):
                try:
                    with page.expect_response(
                        lambda r: API_HOST_LIST in r.url and r.status == 200,
                        timeout=15000,
                    ):
                        page.locator(f'li.semi-page-item[aria-label="Page {page_num}"]').first.click(timeout=8000)
                except Exception as e:
                    print(f"[ui] page {page_num} click err: {e}")

            page.wait_for_timeout(500)

        # Refresh session
        try:
            context.storage_state(path=str(STORAGE))
        except Exception:
            pass
        browser.close()

    return {
        "eventId": activity_id,
        "info": info_body,
        "metrics": metrics_body,
        "currentComponentId": cid,
        "currentComponent": component_meta,
        "captures": captures,
    }


def build_output(raw: dict) -> dict:
    info = raw.get("info") or {}
    ag = info.get("AgencyActivity") or {}
    cid = raw.get("currentComponentId")
    comp = raw.get("currentComponent") or {}
    captures = raw.get("captures") or {}

    # Merge all captures for the current component; prefer the largest-Limit response per Offset
    rows_by_host: Dict[str, dict] = {}
    hosts_base: Dict[str, dict] = {}
    for (c, offset), data in captures.items():
        if c != cid:
            continue
        base = data.get("HostBaseInfoMap") or {}
        hosts_base.update(base)
        for r in (data.get("RecordList") or []):
            hid = r.get("HostID")
            if not hid:
                continue
            # Prefer row with non-zero rank / larger diamonds
            prev = rows_by_host.get(hid)
            if prev is None:
                rows_by_host[hid] = r
            else:
                if int(r.get("Diamonds", 0) or 0) > int(prev.get("Diamonds", 0) or 0):
                    rows_by_host[hid] = r

    creators = []
    for hid, r in rows_by_host.items():
        # RecordList[*].UserBaseInfo has the basics (display_id/avatar/nickname).
        # HostBaseInfoMap entry has additional live-state fields (IsLive, CreatorID, ...).
        # Merge with host_base providing the live fields, ubi taking priority for renames.
        ubi = r.get("UserBaseInfo") or {}
        host_base = hosts_base.get(hid) or {}
        merged = {**host_base, **ubi}
        live_seconds = int(r.get("LiveDuration", 0) or 0)
        creators.append({
            "rank": int(r.get("HostRank", 0) or 0),
            "hostId": hid,
            "username": merged.get("display_id") or "",
            "nickname": merged.get("nickname") or "",
            "avatar": merged.get("avatar") or "",
            "isLive": bool(merged.get("IsLive", False)),
            "score": int(r.get("ActivityScores", 0) or 0),
            "diamonds": int(r.get("Diamonds", 0) or 0),
            "pkDiamond": int(r.get("PKDiamond", 0) or 0),
            "crossCountryPkDiamond": int(r.get("CrossCountryPKDiamond", 0) or 0),
            "pkCount": int(r.get("PKCount", 0) or 0),
            "winnerPkCount": int(r.get("WinnerPKCount", 0) or 0),
            "liveDurationSec": live_seconds,
            "validLiveDayCount": int(r.get("ValidLiveDayCount", 0) or 0),
            "distanceFromLastPlace": int(r.get("DistanceFromLastPlace", 0) or 0),
        })

    # Sort by rank ascending (0 = unranked goes to end)
    creators.sort(key=lambda c: (c["rank"] if c["rank"] > 0 else 10**9, -c["score"]))

    # Event meta
    event_name = ag.get("Name") or ag.get("ActivityName") or ""
    event_start = int(ag.get("StartTime", 0) or 0)
    event_end = int(ag.get("EndTime", 0) or 0)
    stage_start = int(comp.get("StartTime", 0) or 0)
    stage_end = int(comp.get("EndTime", 0) or 0)

    # Aggregate totals prefer live metrics over stale info payload
    metrics = raw.get("metrics") or {}
    metrics_map = {int(m.get("MetricsKey", 0) or 0): int(m.get("MetricsValue", 0) or 0)
                   for m in (metrics.get("MetricsList") or [])}
    total_diamonds = metrics_map.get(METRIC_TOTAL_DIAMONDS, int(ag.get("ActivityDiamonds", 0) or 0))
    total_scores = int(ag.get("ActivityScores", 0) or 0) or sum(c["score"] for c in creators)

    return {
        "generatedAt": datetime.now(JST).isoformat(timespec="seconds"),
        "eventId": raw.get("eventId"),
        "eventName": event_name,
        "eventStart": jst_iso(event_start) if event_start else None,
        "eventEnd": jst_iso(event_end) if event_end else None,
        "stageComponentId": cid,
        "stageStart": jst_iso(stage_start) if stage_start else None,
        "stageEnd": jst_iso(stage_end) if stage_end else None,
        "totalParticipants": len(creators),
        "liveNow": sum(1 for c in creators if c["isLive"]),
        "totalDiamonds": total_diamonds,
        "totalScores": total_scores,
        "creators": creators,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scrape_event.py <ActivityID> [--slug=<slug>]")
        sys.exit(1)
    activity_id = sys.argv[1]
    slug = "newstarcup"
    for a in sys.argv[2:]:
        if a.startswith("--slug="):
            slug = a.split("=", 1)[1]

    if not STORAGE.exists():
        print(f"❌ {STORAGE} not found — run login.py first")
        sys.exit(1)

    headless = os.environ.get("HEADLESS", "1") != "0"

    raw = scrape(activity_id, headless=headless)
    out = build_output(raw)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    latest = OUT_DIR / f"{slug}.json"
    # Per-stage archive — filename preserves stage start date
    stage_start = out.get("stageStart") or ""
    stage_key = stage_start[:10].replace("-", "") if stage_start else datetime.now(JST).strftime("%Y%m%d")
    archive = OUT_DIR / f"{slug}_{stage_key}.json"

    out_str = json.dumps(out, ensure_ascii=False, indent=2)
    latest.write_text(out_str)
    archive.write_text(out_str)

    print(f"\n=== {out['eventName']} stage={out['stageStart']}→{out['stageEnd']} ===")
    print(f"participants={out['totalParticipants']} live={out['liveNow']} totalDiamonds={out['totalDiamonds']}")
    for c in out["creators"][:10]:
        live = "🔴" if c["isLive"] else "  "
        print(f"  #{c['rank']:>3} {live} {c['nickname']:<20} @{c['username']:<20} {c['score']:>8,}pt (diamonds={c['diamonds']} pk={c['pkDiamond']})")


if __name__ == "__main__":
    main()
