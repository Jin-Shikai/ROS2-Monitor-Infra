#!/usr/bin/env bash
# E4 — Multi-robot fleet property.
# Usage: eval/e4/run.sh
#   USE_RVIZ=True eval/e4/run.sh          # GUI run for screenshots
#   SEP_MIN=1.2 eval/e4/run.sh            # different separation threshold
#
# Brings up Gazebo + two namespaced Nav2 stacks in the custom corridor world
# (eval/e4/fleet_launch.py: single /clock bridge), publishes both AMCL
# initial poses during bringup, attaches the monitor (collection) and
# node_runner (evaluation, via MQTT on 1884), then executes the two-leg
# crossing patrol and checks every verdict against the recorded oracle /
# mission ground truth.
set -euo pipefail

cd "$(dirname "$0")/../.."
SEP_MIN="${SEP_MIN:-1.0}"
SPEED_MAX="${SPEED_MAX:-0.3}"
USE_RVIZ="${USE_RVIZ:-False}"
CANCEL_AFTER="${CANCEL_AFTER:-120}"
RUN_DIR="eval/e4/results/run_$(date +%Y%m%d_%H%M%S)"
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
  echo "sep_min_m: $SEP_MIN"
  echo "speed_max_mps: $SPEED_MAX"
  echo "cancel_after_sec: $CANCEL_AFTER"
} > "$RUN_DIR/env.txt"

# Project the deployment JSON into the collection and evaluation YAML files.
cp eval/e4/request.json "$RUN_DIR/request.json"
python3 monitor/config_gen.py "$RUN_DIR/request.json" -o "$RUN_DIR" \
  --var "RUN_DIR=$RUN_DIR" --var "SEP_MIN=$SEP_MIN" \
  --var "SPEED_MAX=$SPEED_MAX" > "$RUN_DIR/config_gen.log"

# Purge leftovers of earlier simulation sessions. This includes the ros2
# launch parent itself: a parent whose children have exited can still retain
# stale ROS discovery state and break BasicNavigator lifecycle service calls.
purge_sim() {
  eval/e4/cleanup.sh --quiet
}
purge_sim
sleep 1

mosquitto -c eval/e4/mosquitto.conf > "$RUN_DIR/broker.log" 2>&1 &
BROKER_PID=$!

ros2 launch eval/e4/fleet_launch.py \
  world:="$WORLD" map:="$MAP" use_rviz:="$USE_RVIZ" \
  params_file:="$PWD/eval/e4/nav2_params.yaml" \
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

# Simulator ground truth (independent of AMCL): the separation verdicts are
# additionally validated against the robots' physical world poses.
python3 eval/e4/gt_logger.py --out "$RUN_DIR/gt_poses.csv" \
  > "$RUN_DIR/gt_logger.log" 2>&1 &
GT_PID=$!

cleanup() {
  kill -INT "$MON_PID" "$RUNNER_PID" "$NAV_PID" "$GT_PID" 2>/dev/null || true
  kill "$SAMPLER_PID" "$BROKER_PID" 2>/dev/null || true
  sleep 3
  purge_sim
}
trap cleanup EXIT

active_count() {
  grep -c "Managed nodes are active" "$RUN_DIR/nav2.log" 2>/dev/null || true
}

# Both localization stacks first; their AMCLs must receive the per-robot
# initial poses while the navigation costmaps are still waiting for the
# map->base_link transform (the shared params file cannot preset two
# different poses).
echo "E4: waiting for localization stacks (results: $RUN_DIR)"
for _ in $(seq 1 90); do [ "$(active_count)" -ge 2 ] && break; sleep 2; done
[ "$(active_count)" -ge 2 ] || {
  echo "localization did not become active; aborting." >&2
  exit 1
}

COV="[0.25,0,0,0,0,0, 0,0.25,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0.068]"
ros2 topic pub --once /robot1/initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  "{header: {frame_id: map}, pose: {pose: {position: {x: -2.0, y: -0.5}, orientation: {w: 1.0}}, covariance: $COV}}" > /dev/null
ros2 topic pub --once /robot2/initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  "{header: {frame_id: map}, pose: {pose: {position: {x: 2.5, y: 0.0}, orientation: {z: 1.0, w: 0.0}}, covariance: $COV}}" > /dev/null
echo "E4: initial poses published"

echo "E4: waiting for navigation stacks"
for _ in $(seq 1 90); do [ "$(active_count)" -ge 4 ] && break; sleep 2; done
[ "$(active_count)" -ge 4 ] || {
  echo "navigation did not become active; aborting." >&2
  exit 1
}
sleep 15

# The mission uses bounded AMCL-pose + action-server readiness checks rather
# than lifecycle get_state services, which can lose responses in this composed
# Fast DDS setup. Retrying is still safe only before "starting leg 1".
echo "E4: running mission"
MISSION_OK=0
for attempt in 1 2; do
  if timeout 600 env PYTHONUNBUFFERED=1 \
      python3 eval/e4/mission.py --log "$RUN_DIR/mission_log.json" \
      --cancel-after "$CANCEL_AFTER" \
      2>&1 | tee "$RUN_DIR/mission.log"; then
    MISSION_OK=1
    break
  fi
  if grep -q "starting leg 1" "$RUN_DIR/mission.log"; then
    echo "mission failed after goals were sent; not retrying" >&2
    break
  fi
  echo "mission attempt $attempt did not start; retrying" >&2
done
[ "$MISSION_OK" = 1 ] || echo "mission failed" >&2

# Ordered shutdown: drain in-flight records, then monitor, then runner.
sleep 3
kill -INT "$MON_PID" 2>/dev/null || true
wait "$MON_PID" 2>/dev/null || true
sleep 2
kill -INT "$RUNNER_PID" 2>/dev/null || true
wait "$RUNNER_PID" 2>/dev/null || true
wait "$SAMPLER_PID" 2>/dev/null || true
kill -INT "$GT_PID" 2>/dev/null || true
kill -INT "$NAV_PID" 2>/dev/null || true
sleep 5
kill "$BROKER_PID" 2>/dev/null || true
purge_sim
trap - EXIT

RECORDS=$(ls -t "$RUN_DIR"/e4mon_*.jsonl | grep -v verdicts_ | head -1)
SPEED_R1=$(ls -t "$RUN_DIR"/verdicts_speed_r1_*.jsonl | head -1)
SPEED_R2=$(ls -t "$RUN_DIR"/verdicts_speed_r2_*.jsonl | head -1)
SEPARATION=$(ls -t "$RUN_DIR"/verdicts_separation_*.jsonl | head -1)

STATUS=0

# P1a/P1b: per-robot speed verdicts vs. the offline oracle on each robot's
# recorded /cmd_vel stream (also demonstrates namespace isolation: a foreign
# record contributing to the wrong stream would break the 1:1 match).
python3 eval/common/analyze_run.py \
  --records "$RECORDS" --verdicts "$SPEED_R1" \
  --field twist.linear.x --threshold "$SPEED_MAX" --source /robot1/cmd_vel \
  --proc "$RUN_DIR/proc.csv" \
  --out "$RUN_DIR/metrics_speed_r1.json" || STATUS=1

python3 eval/common/analyze_run.py \
  --records "$RECORDS" --verdicts "$SPEED_R2" \
  --field twist.linear.x --threshold "$SPEED_MAX" --source /robot2/cmd_vel \
  --out "$RUN_DIR/metrics_speed_r2.json" || STATUS=1

# P2: fleet separation verdicts vs. the offline distance oracle and the
# per-leg mission expectation.
python3 eval/e4/check_separation.py \
  --records "$RECORDS" --verdicts "$SEPARATION" \
  --min-distance "$SEP_MIN" --mission-log "$RUN_DIR/mission_log.json" \
  --out "$RUN_DIR/separation.json" || STATUS=1

# P2 (independent): violation episodes vs. simulator ground-truth poses.
python3 eval/e4/check_gt.py \
  --gt "$RUN_DIR/gt_poses.csv" --verdicts "$SEPARATION" \
  --min-distance "$SEP_MIN" --mission-log "$RUN_DIR/mission_log.json" \
  --out "$RUN_DIR/gt.json" || STATUS=1

echo "E4 done (status=$STATUS): $RUN_DIR"
exit "$STATUS"
