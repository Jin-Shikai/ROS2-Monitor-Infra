#!/usr/bin/env bash
# Stop processes left by an interrupted E2 run and release its MQTT port.
set -u

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

PATTERNS=(
  "[d]emo/common/topic_robot.py cmd-velocity-cycle"
  "[d]emo/common/reset_robot.py"
  "[e]val/e2/action_robot.py"
  "[m]onitor/node_runner.py -c eval/e2/results/"
  "[m]onitor/monitor_node.py -c eval/e2/results/"
  "[e]val/common/proc_sampler.py.*eval/e2/results/"
  "[m]osquitto -c eval/e2/mosquitto.conf"
)

PROTECTED_PIDS=" $$ "
ancestor="$PPID"
while [ "$ancestor" -gt 1 ] 2>/dev/null; do
  PROTECTED_PIDS+="$ancestor "
  ancestor="$(ps -o ppid= -p "$ancestor" 2>/dev/null | tr -d ' ')"
  [ -n "$ancestor" ] || break
done

matching_pids() {
  local pattern="$1" pid
  while read -r pid; do
    [ -n "$pid" ] || continue
    case "$PROTECTED_PIDS" in *" $pid "*) ;; *) echo "$pid" ;; esac
  done < <(pgrep -f "$pattern" 2>/dev/null || true)
}

signal_matches() {
  local signal="$1" pattern pid
  for pattern in "${PATTERNS[@]}"; do
    while read -r pid; do
      [ -n "$pid" ] && kill "-$signal" "$pid" 2>/dev/null || true
    done < <(matching_pids "$pattern")
  done
}

[ "$QUIET" -eq 1 ] || echo "E2 cleanup: requesting process shutdown"
signal_matches TERM
sleep 2
signal_matches KILL
sleep 1

REMAINING=0
for pattern in "${PATTERNS[@]}"; do
  [ -z "$(matching_pids "$pattern")" ] || REMAINING=1
done
if ss -ltn 2>/dev/null | grep -qE ':[1]884[[:space:]]'; then
  REMAINING=1
  [ "$QUIET" -eq 1 ] || echo "E2 cleanup: TCP port 1884 is still in use" >&2
fi
[ "$REMAINING" -eq 0 ] || { [ "$QUIET" -eq 1 ] || echo "E2 cleanup: incomplete" >&2; exit 1; }
[ "$QUIET" -eq 1 ] || echo "E2 cleanup: clean (including TCP port 1884)"
