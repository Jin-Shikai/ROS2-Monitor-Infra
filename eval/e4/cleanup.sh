#!/usr/bin/env bash
# Stop every process that can be left behind by an E4 simulation run.
#
# This intentionally targets the shared Nav2 / Gazebo simulation processes as
# well as E4-owned processes. Run it only when no other local Nav2 simulation
# needs to be kept alive.
set -u

QUIET=0
if [ "${1:-}" = "--quiet" ]; then
  QUIET=1
fi

PATTERNS=(
  "[e]val/e4/mission.py"
  "[e]val/e4/gt_logger.py"
  "[m]onitor/node_runner.py -c eval/e4/results/"
  "[m]onitor/monitor_node.py -c eval/e4/results/"
  "[e]val/common/proc_sampler.py.*eval/e4/results/"
  "[t]ail -f.*eval/e4/results/"
  "[m]osquitto -c eval/e4/mosquitto.conf"
  "[f]leet_launch.py"
  "[c]omponent_container"
  "[g]z sim"
  "[r]viz2"
  "[r]obot_state_publisher"
  "[p]arameter_bridge"
)

# Never signal this script, its caller (for example run.sh), or any ancestor
# terminal / IDE task whose command line happens to contain a target name.
PROTECTED_PIDS=" $$ "
ancestor="$PPID"
while [ "$ancestor" -gt 1 ] 2>/dev/null; do
  PROTECTED_PIDS+="$ancestor "
  ancestor="$(ps -o ppid= -p "$ancestor" 2>/dev/null | tr -d ' ')"
  [ -n "$ancestor" ] || break
done

is_protected() {
  case "$PROTECTED_PIDS" in
    *" $1 "*) return 0 ;;
    *) return 1 ;;
  esac
}

matching_pids() {
  local pattern="$1"
  local pid
  while read -r pid; do
    [ -n "$pid" ] || continue
    is_protected "$pid" || echo "$pid"
  done < <(pgrep -f "$pattern" 2>/dev/null || true)
}

signal_matches() {
  local signal="$1"
  local pattern
  local pid
  for pattern in "${PATTERNS[@]}"; do
    while read -r pid; do
      [ -n "$pid" ] && kill "-$signal" "$pid" 2>/dev/null || true
    done < <(matching_pids "$pattern")
  done
}

[ "$QUIET" -eq 1 ] || echo "E4 cleanup: requesting process shutdown"
signal_matches TERM
sleep 3

# ros2 launch and composed Nav2 containers occasionally ignore TERM while
# their event loops are shutting down. Escalate only processes still matching
# the same narrow E4 / simulation patterns.
signal_matches KILL
sleep 1

REMAINING=0
for pattern in "${PATTERNS[@]}"; do
  matches="$(matching_pids "$pattern")"
  if [ -n "$matches" ]; then
    REMAINING=1
    if [ "$QUIET" -ne 1 ]; then
      while read -r pid; do
        ps -p "$pid" -o pid=,ppid=,stat=,cmd=
      done <<< "$matches"
    fi
  fi
done

if ss -ltn 2>/dev/null | grep -qE ':[1]884[[:space:]]'; then
  REMAINING=1
  [ "$QUIET" -eq 1 ] || echo "E4 cleanup: TCP port 1884 is still in use" >&2
fi

if [ "$REMAINING" -ne 0 ]; then
  [ "$QUIET" -eq 1 ] || echo "E4 cleanup: incomplete" >&2
  exit 1
fi

[ "$QUIET" -eq 1 ] || echo "E4 cleanup: clean (including TCP port 1884)"
