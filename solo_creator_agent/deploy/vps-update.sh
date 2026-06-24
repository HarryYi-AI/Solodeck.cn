#!/usr/bin/env bash
# Run ON YOUR VPS inside the heikesong repo root.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

echo "==> pull latest main"
git pull origin main

echo "==> install python deps"
python3 -m pip install -r solo_creator_agent/requirements.txt

echo "==> optional: rebuild frontend (only if you serve dist from VPS; Cloudflare Pages usually builds in CI)"
if command -v npm >/dev/null 2>&1 && [[ "${BUILD_FRONTEND:-0}" == "1" ]]; then
  npm ci
  npm run build
fi

echo "==> restart API (adjust service name if different)"
if systemctl is-active --quiet solodeck-api 2>/dev/null; then
  sudo systemctl restart solodeck-api
  sudo systemctl status solodeck-api --no-pager
else
  echo "solodeck-api service not found. Start manually:"
  echo "  cd $REPO_ROOT"
  echo "  python3 -m uvicorn solo_creator_agent.api_spa:app --host 127.0.0.1 --port 8787"
fi

echo "==> health check"
curl -fsS http://127.0.0.1:8787/api/health && echo
