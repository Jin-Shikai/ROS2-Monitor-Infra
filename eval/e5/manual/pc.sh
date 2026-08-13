#!/usr/bin/env bash
# Ubuntu PC entry point for the E5 Gazebo + RViz illustration run.
set -euo pipefail

source "$(dirname "$0")/common.sh"

usage() {
  cat <<'EOF'
Usage: eval/e5/manual/pc.sh ACTION RUN_ID

Actions:
  start       Start Gazebo server/client, two Nav2 stacks, two RViz windows,
              the DDS probe, and ground-truth logging; keep this terminal open
  mission     Run the two-leg crossing mission from a second PC terminal
  status      Show readiness/mission markers and recent PC logs
  stop-probe  Stop the DDS publisher before distributed shutdown
  stop        Stop Gazebo, RViz, Nav2, and remaining PC-side loggers
EOF
}

source_ros() {
  set +u
  source /opt/ros/kilted/setup.bash
  source "${NAV2_WS:-$HOME/ros2_ws}/install/setup.bash"
  set -u
  export PYTHONPATH="$PWD:$PWD/monitor:${PYTHONPATH:-}"
  export PYTHONUNBUFFERED=1
}

ACTION="${1:-}"
[ -n "$ACTION" ] || { usage; exit 2; }
e5_set_run "${2:-}"

case "$ACTION" in
  start)
    e5_refuse_reuse
    if [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
      echo "No graphical display detected; run this from the PC desktop session." >&2
      exit 1
    fi
    source_ros
    e5_prepare_config python3
    mkdir -p "$REMOTE_RUN/pc"

    WORLD="${NAV2_WS:-$HOME/ros2_ws}"/src/my_nav2_worlds/worlds/simple_nav_world.sdf
    MAP="${NAV2_WS:-$HOME/ros2_ws}"/src/my_nav2_worlds/maps/simple_nav_world.yaml
    SIM_DIR="$(ros2 pkg prefix nav2_minimal_tb3_sim)/share/nav2_minimal_tb3_sim"
    export GZ_SIM_RESOURCE_PATH="$SIM_DIR/models:$(dirname "$SIM_DIR"):${GZ_SIM_RESOURCE_PATH:-}"

    eval/e4/cleanup.sh --quiet
    {
      date -Is
      uname -a
      echo "run_id: $RUN_ID"
      echo "broker: $BROKER:1884"
      echo "sep_min_m: $SEP_MIN"
      echo "speed_max_mps: $SPEED_MAX"
      echo "display: ${DISPLAY:-${WAYLAND_DISPLAY:-unknown}}"
      echo "ros_distro: ${ROS_DISTRO:-unknown}"
    } > "$REMOTE_RUN/pc/env.txt"

    NAV_PID=""
    GUI_PID=""
    PROBE_PID=""
    GT_PID=""
    SAMPLER_PID=""
    PROBE_STOPPED=0
    CLEANED=0

    stop_pid() {
      local signal="$1"
      local pid="$2"
      [ -n "$pid" ] || return 0
      kill "-$signal" "$pid" 2>/dev/null || true
    }

    wait_pid_bounded() {
      local pid="$1"
      local limit="${2:-15}"
      local count=0
      [ -n "$pid" ] || return 0
      while kill -0 "$pid" 2>/dev/null && [ "$count" -lt "$limit" ]; do
        sleep 1
        count=$((count + 1))
      done
      kill -TERM "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    }

    stop_probe() {
      [ "$PROBE_STOPPED" -eq 0 ] || return 0
      stop_pid INT "$PROBE_PID"
      wait_pid_bounded "$PROBE_PID" 10
      PROBE_PID=""
      PROBE_STOPPED=1
      touch "$REMOTE_RUN/control/probe_stopped"
      echo "E5_PC_PROBE_STOPPED"
    }

    cleanup() {
      [ "$CLEANED" -eq 0 ] || return 0
      CLEANED=1
      set +e
      stop_probe
      stop_pid INT "$GT_PID"
      wait_pid_bounded "$GT_PID" 10
      stop_pid TERM "$SAMPLER_PID"
      wait_pid_bounded "$SAMPLER_PID" 5
      stop_pid INT "$GUI_PID"
      wait_pid_bounded "$GUI_PID" 10
      stop_pid INT "$NAV_PID"
      wait_pid_bounded "$NAV_PID" 20
      eval/e4/cleanup.sh --quiet
      touch "$REMOTE_RUN/control/pc_stopped"
      echo "E5_PC_DONE"
    }
    trap cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM

    python3 eval/e5/dds_probe.py --rate 5 \
      > "$REMOTE_RUN/pc/dds_probe.log" 2>&1 &
    PROBE_PID=$!

    ros2 launch eval/e4/fleet_launch.py \
      world:="$WORLD" map:="$MAP" use_rviz:=True \
      params_file:="$PWD/eval/e4/nav2_params.yaml" \
      > "$REMOTE_RUN/pc/nav2.log" 2>&1 &
    NAV_PID=$!

    python3 eval/common/ps_proc_sampler.py --pid "$NAV_PID" --include-children \
      --interval 1 --out "$REMOTE_RUN/pc/proc.csv" &
    SAMPLER_PID=$!

    python3 eval/e4/gt_logger.py --out "$REMOTE_RUN/pc/gt_poses.csv" \
      > "$REMOTE_RUN/pc/gt_logger.log" 2>&1 &
    GT_PID=$!

    active_count() {
      grep -c "Managed nodes are active" "$REMOTE_RUN/pc/nav2.log" 2>/dev/null || true
    }

    echo "Waiting for both localization stacks..."
    for _ in $(seq 1 90); do
      kill -0 "$NAV_PID" 2>/dev/null || {
        echo "Nav2 launch exited during localization bring-up." >&2
        exit 1
      }
      [ "$(active_count)" -ge 2 ] && break
      sleep 2
    done
    [ "$(active_count)" -ge 2 ] || {
      echo "Localization did not become active; inspect $REMOTE_RUN/pc/nav2.log" >&2
      exit 1
    }

    gz sim -g > "$REMOTE_RUN/pc/gazebo_gui.log" 2>&1 &
    GUI_PID=$!

    COV="[0.25,0,0,0,0,0, 0,0.25,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0.068]"
    ros2 topic pub --once /robot1/initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
      "{header: {frame_id: map}, pose: {pose: {position: {x: -2.0, y: -0.5}, orientation: {w: 1.0}}, covariance: $COV}}" > /dev/null
    ros2 topic pub --once /robot2/initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
      "{header: {frame_id: map}, pose: {pose: {position: {x: 2.5, y: 0.0}, orientation: {z: 1.0, w: 0.0}}, covariance: $COV}}" > /dev/null

    echo "Waiting for both navigation stacks..."
    for _ in $(seq 1 90); do
      kill -0 "$NAV_PID" 2>/dev/null || {
        echo "Nav2 launch exited during navigation bring-up." >&2
        exit 1
      }
      [ "$(active_count)" -ge 4 ] && break
      sleep 2
    done
    [ "$(active_count)" -ge 4 ] || {
      echo "Navigation did not become active; inspect $REMOTE_RUN/pc/nav2.log" >&2
      exit 1
    }
    sleep 15

    touch "$REMOTE_RUN/control/pc_ready"
    echo "E5_PC_READY"

    while [ ! -e "$REMOTE_RUN/control/stop" ]; do
      kill -0 "$NAV_PID" 2>/dev/null || {
        echo "Nav2 launch exited unexpectedly." >&2
        exit 1
      }
      if [ -e "$REMOTE_RUN/control/stop_probe" ] && [ "$PROBE_STOPPED" -eq 0 ]; then
        stop_probe
      fi
      sleep 1
    done
    ;;
  mission)
    source_ros
    e5_require_started pc_ready
    if [ -e "$REMOTE_RUN/control/mission_running" ]; then
      echo "The mission is already running." >&2
      exit 1
    fi
    if [ -e "$REMOTE_RUN/control/mission_done" ]; then
      echo "The mission has already completed for $RUN_ID; use a fresh RUN_ID to repeat it." >&2
      exit 1
    fi
    touch "$REMOTE_RUN/control/mission_running"
    mission_cleanup() { rm -f "$REMOTE_RUN/control/mission_running"; }
    trap mission_cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    echo "Starting the two-leg crossing mission..."
    timeout 600 env PYTHONUNBUFFERED=1 python3 eval/e4/mission.py \
      --log "$REMOTE_RUN/pc/mission_log.json" --cancel-after "${CANCEL_AFTER:-180}" \
      2>&1 | tee "$REMOTE_RUN/pc/mission.log"
    touch "$REMOTE_RUN/control/mission_done"
    echo "E5_PC_MISSION_DONE"
    ;;
  status)
    e5_show_markers
    echo
    if [ -f "$REMOTE_RUN/pc/nav2.log" ]; then
      echo "Nav2 active messages: $(grep -c 'Managed nodes are active' "$REMOTE_RUN/pc/nav2.log" 2>/dev/null || true)"
      tail -n 8 "$REMOTE_RUN/pc/nav2.log"
    fi
    if [ -f "$REMOTE_RUN/pc/mission.log" ]; then
      echo
      tail -n 12 "$REMOTE_RUN/pc/mission.log"
    fi
    ;;
  stop-probe)
    e5_require_started pc_ready
    touch "$REMOTE_RUN/control/stop_probe"
    echo "Requested DDS probe shutdown; wait for probe_stopped."
    ;;
  stop)
    e5_require_started pc_ready
    if [ -e "$REMOTE_RUN/control/mission_running" ]; then
      echo "Warning: the mission is still running and will be interrupted." >&2
    fi
    touch "$REMOTE_RUN/control/stop"
    echo "Requested PC simulation shutdown."
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
