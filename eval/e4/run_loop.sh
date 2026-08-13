#!/usr/bin/env bash
# E4 as a WebUI application: Gazebo + two namespaced Nav2 stacks (with RViz)
# plus the endless crossing patrol. This is the "ROS application" command for
# the E4 host in the WebUI; it only brings up the simulation and drives the
# robots. The monitor, broker, converter, and verdict runtimes are started
# separately from the WebUI topology.
#
#   eval/e4/run_loop.sh                  # Gazebo GUI + RViz on, patrol forever
#   USE_RVIZ=False eval/e4/run_loop.sh   # no RViz windows
#   USE_GZ_GUI=False eval/e4/run_loop.sh # no Gazebo window
#
# The WebUI stop button (SIGINT/SIGTERM to this process group) ends the run:
# the mission cancels in-flight goals and eval/e4/cleanup.sh purges Gazebo,
# Nav2, and RViz leftovers.
set -euo pipefail

cd "$(dirname "$0")/../.."
USE_RVIZ="${USE_RVIZ:-True}"
USE_GZ_GUI="${USE_GZ_GUI:-True}"
CANCEL_AFTER="${CANCEL_AFTER:-120}"
RUN_DIR="eval/e4/results/webui_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUN_DIR"

# ROS setup scripts reference unset variables; relax nounset while sourcing.
set +u
source /opt/ros/kilted/setup.bash
source "${NAV2_WS:-$HOME/ros2_ws}/install/setup.bash"
set -u

WORLD="${NAV2_WS:-$HOME/ros2_ws}"/src/my_nav2_worlds/worlds/simple_nav_world.sdf
MAP="${NAV2_WS:-$HOME/ros2_ws}"/src/my_nav2_worlds/maps/simple_nav_world.yaml

# Purge leftovers of earlier simulation sessions. The port-1884 check inside
# cleanup.sh may fail while a WebUI broker is running; that is fine here.
eval/e4/cleanup.sh --quiet || true
sleep 1

echo "E4 WebUI app: starting Gazebo + two Nav2 stacks (logs: $RUN_DIR)"
ros2 launch eval/e4/fleet_launch.py \
  world:="$WORLD" map:="$MAP" use_rviz:="$USE_RVIZ" \
  params_file:="$PWD/eval/e4/nav2_params.yaml" \
  > "$RUN_DIR/nav2.log" 2>&1 &
NAV_PID=$!

# fleet_launch starts the Gazebo *server* only (gz sim -s). Attach the GUI
# client once the server publishes its world so a Gazebo window appears.
GZ_GUI_PID=""
if [ "$USE_GZ_GUI" = "True" ]; then
  (
    for _ in $(seq 1 60); do
      gz topic -l 2>/dev/null | grep -q clock && break
      sleep 2
    done
    exec gz sim -g
  ) > "$RUN_DIR/gz_gui.log" 2>&1 &
  GZ_GUI_PID=$!
fi

MISSION_PID=""
cleanup() {
  trap - INT TERM EXIT
  if [ -n "$MISSION_PID" ]; then
    kill -INT "$MISSION_PID" 2>/dev/null || true
  fi
  if [ -n "$GZ_GUI_PID" ]; then
    kill -INT "$GZ_GUI_PID" 2>/dev/null || true
  fi
  kill -INT "$NAV_PID" 2>/dev/null || true
  sleep 3
  eval/e4/cleanup.sh --quiet || true
  echo "E4 WebUI app: stopped."
}
trap cleanup INT TERM EXIT

active_count() {
  grep -c "Managed nodes are active" "$RUN_DIR/nav2.log" 2>/dev/null || true
}

# Both localization stacks first; their AMCLs must receive the per-robot
# initial poses while the navigation costmaps are still waiting for the
# map->base_link transform (the shared params file cannot preset two
# different poses).
echo "E4 WebUI app: waiting for both localization stacks..."
for _ in $(seq 1 90); do [ "$(active_count)" -ge 2 ] && break; sleep 2; done
[ "$(active_count)" -ge 2 ] || {
  echo "localization did not become active; see $RUN_DIR/nav2.log" >&2
  exit 1
}

COV="[0.25,0,0,0,0,0, 0,0.25,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0.068]"
ros2 topic pub --once /robot1/initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  "{header: {frame_id: map}, pose: {pose: {position: {x: -2.0, y: -0.5}, orientation: {w: 1.0}}, covariance: $COV}}" > /dev/null
ros2 topic pub --once /robot2/initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  "{header: {frame_id: map}, pose: {pose: {position: {x: 2.5, y: 0.0}, orientation: {z: 1.0, w: 0.0}}, covariance: $COV}}" > /dev/null
echo "E4 WebUI app: initial poses published"

echo "E4 WebUI app: waiting for both navigation stacks..."
for _ in $(seq 1 90); do [ "$(active_count)" -ge 4 ] && break; sleep 2; done
[ "$(active_count)" -ge 4 ] || {
  echo "navigation did not become active; see $RUN_DIR/nav2.log" >&2
  exit 1
}
sleep 15

echo "E4 WebUI app: starting the endless crossing patrol (use the WebUI stop button to end it)"
PYTHONUNBUFFERED=1 python3 eval/e4/mission.py \
  --log "$RUN_DIR/mission_log.json" --cancel-after "$CANCEL_AFTER" --loop &
MISSION_PID=$!
wait "$MISSION_PID"
