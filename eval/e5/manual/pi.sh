#!/usr/bin/env bash
# Raspberry Pi entry point for a manually controlled E5 run.
set -euo pipefail

source "$(dirname "$0")/common.sh"

usage() {
  cat <<'EOF'
Usage: eval/e5/manual/pi.sh ACTION RUN_ID

Actions:
  start         Start Mosquitto, monitor_node, and the Pi reference runner
  status        Show control markers and recent tier logs
  stop-monitor  Stop monitor_node after the PC probe has stopped
  stop-all      Stop the reference runner and Mosquitto
EOF
}

ACTION="${1:-}"
[ -n "$ACTION" ] || { usage; exit 2; }
e5_set_run "${2:-}"

case "$ACTION" in
  start)
    e5_refuse_reuse
    e5_prepare_config python3
    echo "Pi E5 run: $RUN_ID (broker $BROKER:1884)"
    echo "This terminal must remain open. Logs: $REMOTE_RUN/pi/monitor.log"
    exec bash eval/e5/pi_tier.sh "$REMOTE_RUN"
    ;;
  status)
    e5_show_markers
    echo
    tail -n 8 "$REMOTE_RUN/pi/monitor.log" 2>/dev/null || true
    tail -n 8 "$REMOTE_RUN/pi/broker.log" 2>/dev/null || true
    ;;
  stop-monitor)
    e5_require_started pi_ready
    touch "$REMOTE_RUN/control/stop_monitor"
    echo "Requested monitor shutdown; wait for the monitor_stopped marker."
    ;;
  stop-all)
    e5_require_started pi_ready
    if [ ! -e "$REMOTE_RUN/control/monitor_stopped" ]; then
      echo "Stop the monitor first and wait for monitor_stopped." >&2
      exit 1
    fi
    touch "$REMOTE_RUN/control/stop_all"
    echo "Requested Pi reference-runner and broker shutdown."
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
