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
RUN_DIR="eval/e3/results/run_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUN_DIR"

# ROS setup scripts reference unset variables; relax nounset while sourcing.
set +u
source /opt/ros/kilted/setup.bash
source /home/shikai/ros2_ws/install/setup.bash
set -u

WORLD=/home/shikai/ros2_ws/src/my_nav2_worlds/worlds/simple_nav_world.sdf
MAP=/home/shikai/ros2_ws/src/my_nav2_worlds/maps/simple_nav_world.yaml

{
  date -Is
  uname -a
  echo "cores: $(nproc)"
  python3 --version
  echo "ros_distro: ${ROS_DISTRO:-unknown}"
  echo "deadline_sec: $DEADLINE"
  echo "headless: $HEADLESS"
} > "$RUN_DIR/env.txt"

sed "s|@RUN_DIR@|$RUN_DIR|" eval/e3/monitor.yaml.in > "$RUN_DIR/monitor.yaml"
sed -e "s|@RUN_DIR@|$RUN_DIR|" -e "s|@DEADLINE@|$DEADLINE|" \
  eval/e3/runner.yaml.in > "$RUN_DIR/runner.yaml"

# Purge leftovers of earlier simulation sessions: a stale nav2 container
# would register duplicate lifecycle nodes and abort the new bringup.
# ([b]racket patterns avoid pkill matching this script's own command line.)
purge_sim() {
  pkill -f "[c]omponent_container" 2>/dev/null || true
  pkill -f "[g]z sim" 2>/dev/null || true
  pkill -f "[r]obot_state_publisher" 2>/dev/null || true
  pkill -f "[p]arameter_bridge" 2>/dev/null || true
}
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

cleanup() {
  kill -INT "$MON_PID" "$RUNNER_PID" "$NAV_PID" 2>/dev/null || true
  kill "$SAMPLER_PID" "$BROKER_PID" 2>/dev/null || true
  sleep 3
  purge_sim
}
trap cleanup EXIT

echo "E3: waiting for Nav2 to become active (results: $RUN_DIR)"
for _ in $(seq 1 90); do
  grep -q "Managed nodes are active" "$RUN_DIR/nav2.log" 2>/dev/null && break
  sleep 2
done
grep -q "Managed nodes are active" "$RUN_DIR/nav2.log" || {
  echo "Nav2 did not become active; aborting." >&2
  exit 1
}
sleep 5

# nav2_simple_commander's activation wait can hang on a service-discovery
# race if it starts during bringup; a bounded retry recovers (no goals have
# been sent when the hang occurs, so a restart is side-effect free).
echo "E3: running mission"
MISSION_OK=0
for attempt in 1 2; do
  if timeout 420 env PYTHONUNBUFFERED=1 \
      python3 eval/e3/mission.py --log "$RUN_DIR/mission_log.json" \
      2>&1 | tee "$RUN_DIR/mission.log"; then
    MISSION_OK=1
    break
  fi
  echo "mission attempt $attempt did not finish; retrying" >&2
done
[ "$MISSION_OK" = 1 ] || echo "mission failed after retries" >&2

# Ordered shutdown: drain in-flight records, then monitor, then runner.
sleep 3
kill -INT "$MON_PID" 2>/dev/null || true
wait "$MON_PID" 2>/dev/null || true
sleep 2
kill -INT "$RUNNER_PID" 2>/dev/null || true
wait "$RUNNER_PID" 2>/dev/null || true
wait "$SAMPLER_PID" 2>/dev/null || true
kill -INT "$NAV_PID" 2>/dev/null || true
sleep 5
kill "$BROKER_PID" 2>/dev/null || true
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

echo "E3 done (status=$STATUS): $RUN_DIR"
exit "$STATUS"
