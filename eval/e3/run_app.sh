#!/usr/bin/env bash
# E3 as a WebUI application: Gazebo + Nav2 (TB3 waffle) in the custom corridor
# world plus the deterministic three-goal mission with scripted route-closing
# obstacle spawns. This is the "ROS application" command for the E3 host in
# the WebUI; it only brings up the simulation and drives the robot. The
# monitor, converter, and verdict runtimes are started separately from the
# WebUI topology playground (see eval/e3/WEBUI.md).
#
#   eval/e3/run_app.sh                    # Gazebo GUI + RViz on (for recording)
#   USE_RVIZ=False eval/e3/run_app.sh     # no RViz window
#   HEADLESS=True eval/e3/run_app.sh      # no Gazebo window
#
# The mission loops: after goal C both barriers are removed, the costmaps
# are cleared, and the robot returns to the start pose before A/B/C repeat.
# The WebUI stop button (SIGINT/SIGTERM to this process group) ends the run
# and eval/e3/cleanup.sh purges any leftovers.
set -euo pipefail

cd "$(dirname "$0")/../.."
HEADLESS="${HEADLESS:-False}"
USE_RVIZ="${USE_RVIZ:-True}"
CANCEL_AFTER="${CANCEL_AFTER:-90}"
RUN_DIR="eval/e3/results/webui_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUN_DIR"

# ROS setup scripts reference unset variables; relax nounset while sourcing.
set +u
source /opt/ros/kilted/setup.bash
source /home/shikai/ros2_ws/install/setup.bash
set -u

# A WebUI server launched from the uv .venv leaks that PATH here, and the
# venv interpreter lacks numpy/rclpy. Drop the virtualenv, then verify.
if [ -n "${VIRTUAL_ENV:-}" ]; then
  PATH="$(printf '%s' "$PATH" | tr ':' '\n' | grep -vF "$VIRTUAL_ENV" | paste -sd':' -)"
  unset VIRTUAL_ENV
fi
python3 -c 'import numpy, rclpy' 2>/dev/null || {
  echo "python3 ($(command -v python3)) lacks numpy/rclpy." >&2
  echo "Start the WebUI server from a ROS-sourced terminal WITHOUT the .venv (run 'deactivate' first)." >&2
  exit 1
}

WORLD=/home/shikai/ros2_ws/src/my_nav2_worlds/worlds/simple_nav_world.sdf
MAP=/home/shikai/ros2_ws/src/my_nav2_worlds/maps/simple_nav_world.yaml

# Purge leftovers of earlier simulation sessions. The port-1884 check inside
# cleanup.sh may fail while an external broker is running; that is fine here.
eval/e3/cleanup.sh --quiet || true
sleep 1

echo "E3: starting Gazebo + Nav2"
ros2 launch nav2_bringup tb3_simulation_launch.py \
  headless:="$HEADLESS" use_rviz:="$USE_RVIZ" \
  world:="$WORLD" map:="$MAP" \
  params_file:="$PWD/eval/e3/nav2_params.yaml" \
  > "$RUN_DIR/nav2.log" 2>&1 &
NAV_PID=$!
MISSION_PID=""

cleanup() {
  trap - INT TERM EXIT
  [ -n "$MISSION_PID" ] && kill -INT "$MISSION_PID" 2>/dev/null || true
  kill -INT "$NAV_PID" 2>/dev/null || true
  sleep 3
  eval/e3/cleanup.sh --quiet || true
  echo "E3: stopped."
}
trap cleanup INT TERM EXIT

active_count() {
  grep -c "Managed nodes are active" "$RUN_DIR/nav2.log" 2>/dev/null || true
}
echo "E3: waiting for Nav2 to become active"
for _ in $(seq 1 90); do [ "$(active_count)" -ge 2 ] && break; sleep 2; done
[ "$(active_count)" -ge 2 ] || {
  echo "Nav2 did not become active; see $RUN_DIR/nav2.log" >&2
  exit 1
}
sleep 5

# mission.py output stays on stdout so goal progress and results appear in
# the WebUI Live log. --loop repeats A/B/C after each reset until Stop.
echo "E3: running mission loop"
PYTHONUNBUFFERED=1 python3 eval/e3/mission.py \
  --log "$RUN_DIR/mission_log.json" \
  --cancel-after "$CANCEL_AFTER" --ready-timeout 60 --loop &
MISSION_PID=$!
wait "$MISSION_PID"
