#!/usr/bin/env bash
set -euo pipefail
FORCE="${1:-}"
TARGET="$(cd "$(dirname "$0")/../.." && pwd)"
PACK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -e "$TARGET/.workbench-version" && "$FORCE" != "--force" ]]; then
  echo "workbench already installed (.workbench-version exists). Use --force to refresh docs." >&2
  exit 1
fi

mkdir -p "$TARGET/agent-workbench-pack"
cp -r "$PACK_ROOT/." "$TARGET/agent-workbench-pack/"
cat "$PACK_ROOT/VERSION" > "$TARGET/.workbench-version"
echo "SoloDeck workbench pack $(cat "$PACK_ROOT/VERSION") installed"
echo "next: python agent-workbench-pack/scripts/init_agent.py"
