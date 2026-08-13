#!/usr/bin/env bash
# E3 — Nav2 single-robot safety supervision.
# Usage: eval/e3/run.sh
#   HEADLESS=False USE_RVIZ=True eval/e3/run.sh   # GUI run for screenshots
#
# Brings up Gazebo + Nav2 in the custom corridor world, attaches the monitor
# (collection) and node_runner (evaluation, via MQTT on 1884), then executes
# the deterministic three-goal mission with scripted obstacle spawns and
# checks every verdict against the recorded oracle / mission ground truth.
set -euo pipefail

cd "$(dirname "$0")/../.."
DEADLINE="${DEADLINE:-35}"
HEADLESS="${HEADLESS:-True}"
USE_RVIZ="${USE_RVIZ:-False}"
CANCEL_AFTER="${CANCEL_AFTER:-90}"
GOAL_TOLERANCE="${GOAL_TOLERANCE:-0.5}"
RUN_DIR="eval/e3/results/run_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUN_DIR"

# ROS setup scripts reference unset variables; relax nounset while sourcing.
set +u
source /opt/ros/kilted/setup.bash
source "${NAV2_WS:-$HOME/ros2_ws}/install/setup.bash"
set -u

WORLD="${NAV2_WS:-$HOME/ros2_ws}"/src/my_nav2_worlds/worlds/simple_nav_world.sdf
MAP="${NAV2_WS:-$HOME/ros2_ws}"/src/my_nav2_worlds/maps/simple_nav_world.yaml

{
  date -Is
  uname -a
  echo "cores: $(nproc)"
  python3 --version
  echo "ros_distro: ${ROS_DISTRO:-unknown}"
  echo "deadline_sec: $DEADLINE"
  echo "cancel_after_sec: $CANCEL_AFTER"
  echo "goal_tolerance_m: $GOAL_TOLERANCE"
  echo "headless: $HEADLESS"
} > "$RUN_DIR/env.txt"

# Project the deployment JSON; --var preserves DEADLINE as a numeric YAML
# value rather than relying on textual substitution in a hand-written file.
cp eval/e3/request.json "$RUN_DIR/request.json"
python3 monitor/config_gen.py "$RUN_DIR/request.json" -o "$RUN_DIR" \
  --var "RUN_DIR=$RUN_DIR" --var "DEADLINE=$DEADLINE" \
  > "$RUN_DIR/config_gen.log"

# Purge leftovers of earlier simulation sessions: a stale nav2 container
# would register duplicate lifecycle nodes and abort the new bringup.
# ([b]racket patterns avoid pkill matching this script's own command line.)
purge_sim() { eval/e3/cleanup.sh --quiet; }
purge_sim
sleep 1

mosquitto -c eval/e3/mosquitto.conf > "$RUN_DIR/broker.log" 2>&1 &
BROKER_PID=$!

ros2 launch nav2_bringup tb3_simulation_launch.py \
  headless:="$HEADLESS" use_rviz:="$USE_RVIZ" \
  world:="$WORLD" map:="$MAP" \
  params_file:="$PWD/eval/e3/nav2_params.yaml" \
  > "$RUN_DIR/nav2.log" 2>&1 &
NAV_PID=$!

python3 monitor/node_runner.py -c "$RUN_DIR/runner.yaml" \
  > "$RUN_DIR/runner.log" 2>&1 &
RUNNER_PID=$!

python3 monitor/monitor_node.py -c "$RUN_DIR/monitor.yaml" \
  > "$RUN_DIR/monitor.log" 2>&1 &
MON_PID=$!

python3 eval/common/proc_sampler.py --pid "$MON_PID" --pid "$RUNNER_PID" \
  --interval 1 --out "$RUN_DIR/proc.csv" &
SAMPLER_PID=$!

# Simulator truth is independent of AMCL and catches a map/initial-pose
# offset even when Nav2 itself reports SUCCEEDED.
python3 eval/e4/gt_logger.py --robots turtlebot3_waffle \
  --out "$RUN_DIR/gt_poses.csv" > "$RUN_DIR/gt_logger.log" 2>&1 &
GT_PID=$!

cleanup() {
  kill -INT "$MON_PID" "$RUNNER_PID" "$NAV_PID" "$GT_PID" 2>/dev/null || true
  kill "$SAMPLER_PID" "$BROKER_PID" 2>/dev/null || true
  sleep 3
  purge_sim
}
trap cleanup EXIT

stop_pid() {
  local pid="$1" signal="${2:-TERM}" ticks="${3:-50}" state
  kill "-$signal" "$pid" 2>/dev/null || true
  for _ in $(seq 1 "$ticks"); do
    kill -0 "$pid" 2>/dev/null || break
    state="$(ps -o stat= -p "$pid" 2>/dev/null || true)"
    [[ "$state" == Z* ]] && break
    sleep 0.1
  done
  state="$(ps -o stat= -p "$pid" 2>/dev/null || true)"
  [ -z "$state" ] || [[ "$state" == Z* ]] || kill -KILL "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}

echo "E3: waiting for Nav2 to become active (results: $RUN_DIR)"
active_count() {
  grep -c "Managed nodes are active" "$RUN_DIR/nav2.log" 2>/dev/null || true
}
for _ in $(seq 1 90); do [ "$(active_count)" -ge 2 ] && break; sleep 2; done
[ "$(active_count)" -ge 2 ] || {
  echo "Nav2 did not become active; aborting." >&2
  exit 1
}
sleep 5

# mission.py avoids lifecycle get_state calls and uses bounded AMCL-pose plus
# NavigateToPose action readiness. Retry only before any goal has been sent.
echo "E3: running mission"
MISSION_OK=0
for attempt in 1 2; do
  if timeout 420 env PYTHONUNBUFFERED=1 \
      python3 eval/e3/mission.py --log "$RUN_DIR/mission_log.json" \
      --cancel-after "$CANCEL_AFTER" \
      2>&1 | tee "$RUN_DIR/mission.log"; then
    MISSION_OK=1
    break
  fi
  if grep -q "nav to point" "$RUN_DIR/mission.log"; then
    echo "mission failed after a goal may have been sent; not retrying" >&2
    break
  fi
  echo "mission attempt $attempt did not start; retrying" >&2
done
[ "$MISSION_OK" = 1 ] || { echo "mission failed" >&2; exit 1; }

# Ordered shutdown: drain in-flight records, then monitor, then runner.
sleep 3
stop_pid "$MON_PID" INT 100
sleep 2
stop_pid "$RUNNER_PID" INT 100
stop_pid "$SAMPLER_PID" TERM 30
stop_pid "$GT_PID" INT 30
stop_pid "$NAV_PID" INT 100
stop_pid "$BROKER_PID" TERM 30
purge_sim
trap - EXIT

RECORDS=$(ls -t "$RUN_DIR"/e3mon_*.jsonl | grep -v verdicts_ | head -1)
SPEED=$(ls -t "$RUN_DIR"/verdicts_speed_*.jsonl | head -1)
NAV=$(ls -t "$RUN_DIR"/verdicts_nav_*.jsonl | head -1)

STATUS=0

# P1: speed verdicts vs. offline oracle on the recorded /cmd_vel stream.
python3 eval/common/analyze_run.py \
  --records "$RECORDS" --verdicts "$SPEED" \
  --field twist.linear.x --threshold 0.2 --source /cmd_vel \
  --proc "$RUN_DIR/proc.csv" \
  --out "$RUN_DIR/metrics_speed.json" || STATUS=1

# P2: nav-goal verdicts vs. the mission log ground truth.
python3 eval/e3/check_goals.py \
  --mission-log "$RUN_DIR/mission_log.json" --verdicts "$NAV" \
  --deadline "$DEADLINE" \
  --out "$RUN_DIR/goals.json" || STATUS=1

# Independent physical check: Gazebo spawn and every successful endpoint
# must agree with the map-frame poses recorded by the mission.
python3 eval/e3/check_physical_poses.py \
  --gt "$RUN_DIR/gt_poses.csv" --mission-log "$RUN_DIR/mission_log.json" \
  --tolerance "$GOAL_TOLERANCE" \
  --out "$RUN_DIR/physical_poses.json" || STATUS=1

# Scenario-value check: A crosses the lower opening, B must be rerouted through
# the upper opening, and C must not cross after both openings are closed.
python3 eval/e3/check_routes.py \
  --gt "$RUN_DIR/gt_poses.csv" --mission-log "$RUN_DIR/mission_log.json" \
  --out "$RUN_DIR/routes.json" || STATUS=1

echo "E3 done (status=$STATUS): $RUN_DIR"
exit "$STATUS"
