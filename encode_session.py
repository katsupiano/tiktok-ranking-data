"""Strip bloat from storage_state*.json, gzip + base64 encode.
Usage: python3 encode_session.py [alpha|ulysses]  (default: alpha)
Output: /tmp/session_<agency>_b64.txt — paste into GitHub Secret."""
import json, base64, gzip, sys
from pathlib import Path

AGENCY = sys.argv[1] if len(sys.argv) > 1 else "alpha"
SRC_MAP = {"alpha": "storage_state.json", "ulysses": "storage_state_ulysses.json"}
SECRET_MAP = {"alpha": "SESSION_STATE_B64", "ulysses": "SESSION_STATE_ULYSSES_B64"}
if AGENCY not in SRC_MAP:
    print(f"unknown agency: {AGENCY}. Use: alpha | ulysses")
    sys.exit(1)

BASE = Path(__file__).parent
SRC = BASE / SRC_MAP[AGENCY]
OUT = Path(f"/tmp/session_{AGENCY}_b64.txt")

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
print(f"Paste into GitHub Secret: {SECRET_MAP[AGENCY]}")
print(f"URL: https://github.com/katsupiano/tiktok-ranking-data/settings/secrets/actions/new")
