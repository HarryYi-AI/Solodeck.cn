#!/usr/bin/env bash
# Start Cloudflare Tunnel connector (no sudo). Requires TUNNEL_TOKEN env var.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CF="${CLOUDFLARED:-$HOME/bin/cloudflared}"
[[ -x "$CF" ]] || CF="/workspace/ylj/bin/cloudflared"
[[ -x "$CF" ]] || { echo "cloudflared not found. Run: curl -L ... -o ~/bin/cloudflared && chmod +x ~/bin/cloudflared"; exit 1; }

if [[ -z "${TUNNEL_TOKEN:-}" ]]; then
  echo "Set TUNNEL_TOKEN from Cloudflare Zero Trust → Networks → Tunnels → solodeck-api → Configure → Install connector"
  echo "Example:"
  echo "  export TUNNEL_TOKEN='eyJh...'"
  echo "  bash solo_creator_agent/deploy/start-cloudflared.sh"
  exit 1
fi

LOG_DIR="${LOG_DIR:-$REPO_ROOT/logs}"
mkdir -p "$LOG_DIR"

if pgrep -f "cloudflared tunnel run" >/dev/null 2>&1; then
  echo "cloudflared already running"
  exit 0
fi

nohup "$CF" tunnel run --token "$TUNNEL_TOKEN" \
  >>"$LOG_DIR/cloudflared.log" 2>&1 &
echo $! >"$LOG_DIR/cloudflared.pid"
sleep 3
echo "Started cloudflared pid $(cat "$LOG_DIR/cloudflared.pid"), log: $LOG_DIR/cloudflared.log"
echo "Verify: curl https://api.solodeck.cn/api/health"
