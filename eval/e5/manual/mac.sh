#!/usr/bin/env bash
# macOS entry point for a manually controlled E5 run.
set -euo pipefail

source "$(dirname "$0")/common.sh"

usage() {
  cat <<'EOF'
Usage: eval/e5/manual/mac.sh ACTION RUN_ID

Actions:
  start   Start the remote verdict runner in this foreground terminal
  status  Show control markers and recent verdict-runner output
  stop    Stop the verdict runner after the Pi monitor has drained
EOF
}

ACTION="${1:-}"
[ -n "$ACTION" ] || { usage; exit 2; }
e5_set_run "${2:-}"
PYTHON_BIN="${E5_MAC_PYTHON:-/opt/homebrew/bin/python3.12}"

case "$ACTION" in
  start)
    e5_refuse_reuse
    [ -x "$PYTHON_BIN" ] || {
      echo "Python not found or not executable: $PYTHON_BIN" >&2
      exit 1
    }
    e5_prepare_config "$PYTHON_BIN"
    echo "Mac E5 run: $RUN_ID (broker $BROKER:1884)"
    echo "This terminal must remain open. Live verdicts are also in runner.log."
    exec env E5_MAC_PYTHON="$PYTHON_BIN" bash eval/e5/mac_tier.sh "$REMOTE_RUN"
    ;;
  status)
    e5_show_markers
    echo
    tail -n 20 "$REMOTE_RUN/mac/runner.log" 2>/dev/null || true
    ;;
  stop)
    e5_require_started mac_ready
    touch "$REMOTE_RUN/control/stop"
    echo "Requested Mac verdict-runner shutdown."
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
