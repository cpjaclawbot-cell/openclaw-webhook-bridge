#!/usr/bin/env bash
set -euo pipefail
TEXT="${1:-}"
LOCAL_AGENT_ID="${LOCAL_AGENT_ID:-main}"
TIMEOUT_SECONDS="${LOCAL_AGENT_TIMEOUT_SECONDS:-45}"

# Route inbound request into local OpenClaw agent and return plain-text answer.
# Requires the local instance to have an agent id available (default: main).
RESP_JSON=$(openclaw agent --agent "$LOCAL_AGENT_ID" --message "$TEXT" --timeout "$TIMEOUT_SECONDS" --json 2>/tmp/oc_bridge_agent_err.log || true)

if [ -z "$RESP_JSON" ]; then
  echo "[openclaw handler] no response (agent command failed): $(cat /tmp/oc_bridge_agent_err.log 2>/dev/null || true)"
  exit 0
fi

# Try to extract common response fields via python to avoid jq dependency.
python3 - <<'PY' "$RESP_JSON"
import json,sys
raw=sys.argv[1]
try:
    obj=json.loads(raw)
except Exception:
    print(raw)
    raise SystemExit(0)

candidates=[]
# best-effort paths seen across CLI outputs
for path in [
    ("reply",),
    ("response",),
    ("result","reply"),
    ("result","response"),
    ("result","text"),
    ("text",),
]:
    cur=obj
    ok=True
    for k in path:
        if isinstance(cur,dict) and k in cur:
            cur=cur[k]
        else:
            ok=False
            break
    if ok and isinstance(cur,str) and cur.strip():
        candidates.append(cur.strip())

if candidates:
    print(candidates[0])
else:
    print(json.dumps(obj)[:2000])
PY
