#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 "$ROOT_DIR/scripts/sync_quad_agent_docs.py" --root "$ROOT_DIR"
python3 "$ROOT_DIR/scripts/build_agent_context.py" --root "$ROOT_DIR" --phase post

echo "Post-session context refreshed under $ROOT_DIR/.harness/context"
