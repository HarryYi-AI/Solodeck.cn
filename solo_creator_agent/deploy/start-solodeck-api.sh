#!/usr/bin/env bash
# Start FastAPI on 127.0.0.1:8787 (no sudo). Run from repo root or anywhere.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-/workspace/ylj/miniconda3/bin/python}"
export PYTHONPATH="$REPO_ROOT"
[[ -f "$REPO_ROOT/.env" ]] && set -a && source "$REPO_ROOT/.env" && set +a

LOG_DIR="${LOG_DIR:-$REPO_ROOT/logs}"
mkdir -p "$LOG_DIR"

if curl -fsS http://127.0.0.1:8787/api/health >/dev/null 2>&1; then
  echo "API already running on 127.0.0.1:8787"
  curl -s http://127.0.0.1:8787/api/health
  exit 0
fi

nohup "$PYTHON" -m uvicorn solo_creator_agent.api_spa:app \
  --host 127.0.0.1 --port 8787 \
  >>"$LOG_DIR/solodeck-api.log" 2>&1 &
echo $! >"$LOG_DIR/solodeck-api.pid"
sleep 2
curl -fsS http://127.0.0.1:8787/api/health
echo
echo "Started API pid $(cat "$LOG_DIR/solodeck-api.pid"), log: $LOG_DIR/solodeck-api.log"
