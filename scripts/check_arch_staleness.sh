#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: bash scripts/check_arch_staleness.sh <pre|post>" >&2
  exit 1
fi

phase="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

case "$phase" in
  pre)
    bash "$SCRIPT_DIR/pre_session.sh"
    ;;
  post)
    bash "$SCRIPT_DIR/post_session.sh"
    ;;
  *)
    echo "Usage: bash scripts/check_arch_staleness.sh <pre|post>" >&2
    exit 1
    ;;
esac

python3 - "$ROOT_DIR/.harness/state/session_metadata.json" <<'PY'
import json
import sys
from pathlib import Path

metadata_path = Path(sys.argv[1])
if not metadata_path.exists():
    raise SystemExit(0)

metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
counts = metadata.get("delta_counts", {})
phase = metadata.get("phase", "unknown")
reference = metadata.get("reference_label", "unknown")
added = counts.get("added", 0)
changed = counts.get("changed", 0)
removed = counts.get("removed", 0)
stale = "yes" if any((added, changed, removed)) else "no"
print(
    f"[arch_staleness] phase={phase} stale_before_refresh={stale} "
    f"reference='{reference}' added={added} changed={changed} removed={removed}"
)
PY
