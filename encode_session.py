"""Strip bloat from storage_state.json, gzip + base64 encode.
Output: /tmp/session_slim_b64.txt (paste into GitHub Secret SESSION_STATE_B64).
Run this whenever the session expires and you re-run login.py."""
import json, base64, gzip
from pathlib import Path

BASE = Path(__file__).parent
SRC = BASE / "storage_state.json"
OUT = Path("/tmp/session_slim_b64.txt")

BLOAT_KEYS = {"__WEBCAST_UNION_PLATFORM_PERSIST___startupApiCache"}
BLOAT_PREFIXES = ("text.", "i18n.", "SLARDAR")

data = json.loads(SRC.read_text())
filtered_ls = [
    item for item in data["origins"][0]["localStorage"]
    if item["name"] not in BLOAT_KEYS
    and not any(item["name"].startswith(p) for p in BLOAT_PREFIXES)
]
slim = {
    "cookies": [c for c in data["cookies"] if "tiktok.com" in c.get("domain", "") or "bytedance" in c.get("domain", "")],
    "origins": [{"origin": data["origins"][0]["origin"], "localStorage": filtered_ls}],
}
gz = gzip.compress(json.dumps(slim).encode())
b64 = base64.b64encode(gz)
OUT.write_bytes(b64)

print(f"Wrote {OUT} ({len(b64):,} bytes, {len(b64)/1024:.1f} KB)")
print(f"Paste into GitHub Secret: SESSION_STATE_B64")
print(f"URL: https://github.com/katsupiano/tiktok-ranking-data/settings/secrets/actions/new")
