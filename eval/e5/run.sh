#!/usr/bin/env bash
# E5 — E4 fleet mission distributed over three physical machines.
#
# PC:  Gazebo + two Nav2 stacks + mission + DDS wall-clock probe
# Pi:  monitor_node + Mosquitto + a Pi-local reference verifier
# Mac: node_runner (official remote verdict tier, kept under live SSH)
#
# Usage: eval/e5/run.sh
# Optional: SEP_MIN=1.0 SPEED_MAX=0.3 CANCEL_AFTER=120 eval/e5/run.sh
set -euo pipefail

cd "$(dirname "$0")/../.."
SEP_MIN="${SEP_MIN:-1.0}"
SPEED_MAX="${SPEED_MAX:-0.3}"
CANCEL_AFTER="${CANCEL_AFTER:-120}"
USE_RVIZ="${USE_RVIZ:-False}"
PI_HOST="${PI_HOST:-pi@raspberrypi.local}"
MAC_HOST="${MAC_HOST:-user@macbook.local}"
BROKER="${BROKER:-192.168.2.18}"
REMOTE_ROOT="${REMOTE_ROOT:-ROS2-Monitor-Infra}"
MAC_PYTHON="${MAC_PYTHON:-/opt/homebrew/bin/python3.12}"
RUN_ID="run_$(date +%Y%m%d_%H%M%S)"
RUN_DIR="eval/e5/results/$RUN_ID"
REMOTE_RUN="eval/e5/results/$RUN_ID"
mkdir -p "$RUN_DIR/pc" "$RUN_DIR/pi" "$RUN_DIR/mac" \
  "$RUN_DIR/pi_reference" "$RUN_DIR/config"

set +u
source /opt/ros/kilted/setup.bash
source "${NAV2_WS:-$HOME/ros2_ws}/install/setup.bash"
set -u
export PYTHONPATH="$PWD:$PWD/monitor:${PYTHONPATH:-}"
export PYTHONUNBUFFERED=1

WORLD="${NAV2_WS:-$HOME/ros2_ws}"/src/my_nav2_worlds/worlds/simple_nav_world.sdf
MAP="${NAV2_WS:-$HOME/ros2_ws}"/src/my_nav2_worlds/maps/simple_nav_world.yaml
SSH_OPTIONS=(-o BatchMode=yes -o ConnectTimeout=8 -o ServerAliveInterval=15 -o ServerAliveCountMax=4)

{
  date -Is
  uname -a
  echo "cores: $(nproc)"
  python3 --version
  echo "ros_distro: ${ROS_DISTRO:-unknown}"
  echo "ros_domain_id: ${ROS_DOMAIN_ID:-0}"
  echo "rmw_implementation: ${RMW_IMPLEMENTATION:-default}"
  echo "pi_host: $PI_HOST"
  echo "mac_host: $MAC_HOST"
  echo "broker: $BROKER:1884"
  echo "sep_min_m: $SEP_MIN"
  echo "speed_max_mps: $SPEED_MAX"
  echo "cancel_after_sec: $CANCEL_AFTER"
  timedatectl status || true
} > "$RUN_DIR/pc/env.txt" 2>&1

cp eval/e5/request.json "$RUN_DIR/request.json"
python3 monitor/config_gen.py "$RUN_DIR/request.json" -o "$RUN_DIR/config" \
  --var "REMOTE_RUN=$REMOTE_RUN" --var "BROKER=$BROKER" \
  --var "SEP_MIN=$SEP_MIN" --var "SPEED_MAX=$SPEED_MAX" \
  > "$RUN_DIR/pc/config_gen.log"

sync_repo() {
  local host="$1"
  rsync -az \
    --exclude='.git/' --exclude='.venv/' --exclude='__pycache__/' \
    --exclude='eval/*/results/' --exclude='Thesis/' --exclude='output/' \
    ./ "$host:$REMOTE_ROOT/"
  ssh "${SSH_OPTIONS[@]}" "$host" \
    "mkdir -p '$REMOTE_ROOT/$REMOTE_RUN/config' '$REMOTE_ROOT/$REMOTE_RUN/control'"
  rsync -az "$RUN_DIR/config/" "$host:$REMOTE_ROOT/$REMOTE_RUN/config/"
}

echo "E5: synchronizing the current working tree to Pi and Mac"
sync_repo "$PI_HOST"
sync_repo "$MAC_HOST"

# Remove only stale E5/simulation processes before starting this run.
PI_HOST="$PI_HOST" MAC_HOST="$MAC_HOST" eval/e5/cleanup.sh >/dev/null 2>&1 || true
eval/e4/cleanup.sh --quiet

PI_SSH_PID=""
MAC_SSH_PID=""
NAV_PID=""
PROBE_PID=""
GT_PID=""
PC_SAMPLER_PID=""
REMOTE_FINISHED=0

remote_touch() {
  local host="$1"
  local marker="$2"
  ssh "${SSH_OPTIONS[@]}" "$host" \
    "touch '$REMOTE_ROOT/$REMOTE_RUN/control/$marker'"
}

wait_remote_marker() {
  local host="$1"
  local marker="$2"
  local limit="${3:-60}"
  local count=0
  while [ "$count" -lt "$limit" ]; do
    if ssh "${SSH_OPTIONS[@]}" "$host" \
        "test -e '$REMOTE_ROOT/$REMOTE_RUN/control/$marker'"; then
      return 0
    fi
    sleep 1
    count=$((count + 1))
  done
  return 1
}

stop_local_pid() {
  local signal="$1"
  local pid="$2"
  [ -n "$pid" ] || return 0
  kill "-$signal" "$pid" 2>/dev/null || true
}

finish_remote() {
  [ "$REMOTE_FINISHED" -eq 0 ] || return 0
  set +e
  remote_touch "$PI_HOST" stop_monitor
  wait_remote_marker "$PI_HOST" monitor_stopped 40
  sleep 2
  remote_touch "$MAC_HOST" stop
  if [ -n "$MAC_SSH_PID" ]; then
    wait "$MAC_SSH_PID"
  fi
  remote_touch "$PI_HOST" stop_all
  if [ -n "$PI_SSH_PID" ]; then
    wait "$PI_SSH_PID"
  fi
  REMOTE_FINISHED=1
  set -e
}

cleanup() {
  set +e
  stop_local_pid INT "$PROBE_PID"
  finish_remote
  stop_local_pid INT "$GT_PID"
  stop_local_pid INT "$NAV_PID"
  stop_local_pid TERM "$PC_SAMPLER_PID"
  sleep 3
  eval/e4/cleanup.sh --quiet
}
trap cleanup EXIT INT TERM

echo "E5: starting Pi broker, monitor, and reference verifier"
ssh "${SSH_OPTIONS[@]}" "$PI_HOST" \
  "cd '$REMOTE_ROOT' && bash eval/e5/pi_tier.sh '$REMOTE_RUN'" \
  > "$RUN_DIR/pc/pi_ssh.log" 2>&1 &
PI_SSH_PID=$!
wait_remote_marker "$PI_HOST" pi_ready 60 || {
  echo "E5: Pi tier did not become ready" >&2
  exit 1
}

echo "E5: starting Mac verifier under a live SSH session"
ssh "${SSH_OPTIONS[@]}" "$MAC_HOST" \
  "cd '$REMOTE_ROOT' && E5_MAC_PYTHON='$MAC_PYTHON' bash eval/e5/mac_tier.sh '$REMOTE_RUN'" \
  > "$RUN_DIR/pc/mac_ssh.log" 2>&1 &
MAC_SSH_PID=$!
wait_remote_marker "$MAC_HOST" mac_ready 60 || {
  echo "E5: Mac tier did not become ready" >&2
  exit 1
}

python3 eval/e5/measure_clock.py --host "$PI_HOST" --count 20 \
  --out "$RUN_DIR/pc/clock_pi_start.json" > /dev/null
python3 eval/e5/measure_clock.py --host "$MAC_HOST" \
  --remote-python "$MAC_PYTHON" --count 20 \
  --out "$RUN_DIR/pc/clock_mac_start.json" > /dev/null

python3 eval/e5/dds_probe.py --rate 5 \
  > "$RUN_DIR/pc/dds_probe.log" 2>&1 &
PROBE_PID=$!

echo "E5: launching the two-robot Nav2 simulation headlessly (results: $RUN_DIR)"
ros2 launch eval/e4/fleet_launch.py \
  world:="$WORLD" map:="$MAP" use_rviz:="$USE_RVIZ" \
  params_file:="$PWD/eval/e4/nav2_params.yaml" \
  > "$RUN_DIR/pc/nav2.log" 2>&1 &
NAV_PID=$!

python3 eval/common/ps_proc_sampler.py --pid "$NAV_PID" --include-children \
  --interval 1 --out "$RUN_DIR/pc/proc.csv" &
PC_SAMPLER_PID=$!

python3 eval/e4/gt_logger.py --out "$RUN_DIR/pc/gt_poses.csv" \
  > "$RUN_DIR/pc/gt_logger.log" 2>&1 &
GT_PID=$!

active_count() {
  grep -c "Managed nodes are active" "$RUN_DIR/pc/nav2.log" 2>/dev/null || true
}

echo "E5: waiting for localization stacks"
for _ in $(seq 1 90); do [ "$(active_count)" -ge 2 ] && break; sleep 2; done
[ "$(active_count)" -ge 2 ] || {
  echo "E5: localization did not become active" >&2
  exit 1
}

COV="[0.25,0,0,0,0,0, 0,0.25,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0.068]"
ros2 topic pub --once /robot1/initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  "{header: {frame_id: map}, pose: {pose: {position: {x: -2.0, y: -0.5}, orientation: {w: 1.0}}, covariance: $COV}}" > /dev/null
ros2 topic pub --once /robot2/initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  "{header: {frame_id: map}, pose: {pose: {position: {x: 2.5, y: 0.0}, orientation: {z: 1.0, w: 0.0}}, covariance: $COV}}" > /dev/null

echo "E5: waiting for navigation stacks"
for _ in $(seq 1 90); do [ "$(active_count)" -ge 4 ] && break; sleep 2; done
[ "$(active_count)" -ge 4 ] || {
  echo "E5: navigation did not become active" >&2
  exit 1
}
sleep 15

echo "E5: running the two-leg fleet mission"
MISSION_OK=0
for attempt in 1 2; do
  if timeout 600 env PYTHONUNBUFFERED=1 \
      python3 eval/e4/mission.py --log "$RUN_DIR/pc/mission_log.json" \
      --cancel-after "$CANCEL_AFTER" \
      2>&1 | tee "$RUN_DIR/pc/mission.log"; then
    MISSION_OK=1
    break
  fi
  if grep -q "starting leg 1" "$RUN_DIR/pc/mission.log"; then
    echo "E5: mission failed after goals were sent; not retrying" >&2
    break
  fi
  echo "E5: mission attempt $attempt did not start; retrying" >&2
done
[ "$MISSION_OK" -eq 1 ] || echo "E5: mission failed; artifacts will still be collected" >&2

python3 eval/e5/measure_clock.py --host "$PI_HOST" --count 20 \
  --out "$RUN_DIR/pc/clock_pi_end.json" > /dev/null
python3 eval/e5/measure_clock.py --host "$MAC_HOST" \
  --remote-python "$MAC_PYTHON" --count 20 \
  --out "$RUN_DIR/pc/clock_mac_end.json" > /dev/null

# Ordered distributed shutdown: publisher/probe, Pi monitor, Mac verifier,
# Pi reference verifier and broker, then the simulator.
stop_local_pid INT "$PROBE_PID"
wait "$PROBE_PID" 2>/dev/null || true
PROBE_PID=""
sleep 3
finish_remote

stop_local_pid INT "$GT_PID"
wait "$GT_PID" 2>/dev/null || true
GT_PID=""
stop_local_pid INT "$NAV_PID"
sleep 5
stop_local_pid TERM "$PC_SAMPLER_PID"
wait "$PC_SAMPLER_PID" 2>/dev/null || true
PC_SAMPLER_PID=""
eval/e4/cleanup.sh --quiet
NAV_PID=""

echo "E5: collecting Pi and Mac artifacts"
rsync -az "$PI_HOST:$REMOTE_ROOT/$REMOTE_RUN/pi/" "$RUN_DIR/pi/"
rsync -az "$PI_HOST:$REMOTE_ROOT/$REMOTE_RUN/pi_reference/" "$RUN_DIR/pi_reference/"
rsync -az "$MAC_HOST:$REMOTE_ROOT/$REMOTE_RUN/mac/" "$RUN_DIR/mac/"

latest() {
  ls -t "$@" 2>/dev/null | head -1
}

RECORDS="$(latest "$RUN_DIR"/pi/e5pi_*.jsonl)"
REMOTE_R1="$(latest "$RUN_DIR"/mac/verdicts_speed_r1_*.jsonl)"
REMOTE_R2="$(latest "$RUN_DIR"/mac/verdicts_speed_r2_*.jsonl)"
REMOTE_SEP="$(latest "$RUN_DIR"/mac/verdicts_separation_*.jsonl)"
REF_R1="$(latest "$RUN_DIR"/pi_reference/verdicts_speed_r1_*.jsonl)"
REF_R2="$(latest "$RUN_DIR"/pi_reference/verdicts_speed_r2_*.jsonl)"
REF_SEP="$(latest "$RUN_DIR"/pi_reference/verdicts_separation_*.jsonl)"

MAC_MINUS_PI="$(python3 - "$RUN_DIR" <<'PY'
import json, statistics, sys
root = sys.argv[1] + "/pc/"
def offset(name):
    with open(root + name, encoding="utf-8") as stream:
        return json.load(stream)["estimate"]["offset_seconds"]
pi = statistics.fmean((offset("clock_pi_start.json"), offset("clock_pi_end.json")))
mac = statistics.fmean((offset("clock_mac_start.json"), offset("clock_mac_end.json")))
print(mac - pi)
PY
)"

STATUS=0

python3 eval/common/analyze_run.py \
  --records "$RECORDS" --verdicts "$REMOTE_R1" \
  --field twist.linear.x --threshold "$SPEED_MAX" --source /robot1/cmd_vel \
  --clock-offset "$MAC_MINUS_PI" --out "$RUN_DIR/metrics_speed_r1_remote.json" \
  || STATUS=1
python3 eval/common/analyze_run.py \
  --records "$RECORDS" --verdicts "$REMOTE_R2" \
  --field twist.linear.x --threshold "$SPEED_MAX" --source /robot2/cmd_vel \
  --clock-offset "$MAC_MINUS_PI" --out "$RUN_DIR/metrics_speed_r2_remote.json" \
  || STATUS=1
python3 eval/e4/check_separation.py \
  --records "$RECORDS" --verdicts "$REMOTE_SEP" \
  --min-distance "$SEP_MIN" --mission-log "$RUN_DIR/pc/mission_log.json" \
  --clock-offset "$MAC_MINUS_PI" --out "$RUN_DIR/separation_remote.json" \
  || STATUS=1
python3 eval/e4/check_gt.py \
  --gt "$RUN_DIR/pc/gt_poses.csv" --verdicts "$REMOTE_SEP" \
  --min-distance "$SEP_MIN" --mission-log "$RUN_DIR/pc/mission_log.json" \
  --out "$RUN_DIR/gt.json" || STATUS=1

for spec in \
  "speed_r1:$REF_R1:$REMOTE_R1" \
  "speed_r2:$REF_R2:$REMOTE_R2" \
  "separation:$REF_SEP:$REMOTE_SEP"; do
  IFS=: read -r name reference remote <<< "$spec"
  python3 eval/common/compare_verdicts.py --a "$reference" --b "$remote" \
    --out "$RUN_DIR/transparency_${name}.json" || STATUS=1
done

python3 eval/e5/analyze_e5.py \
  --records "$RECORDS" \
  --remote-speed-r1 "$REMOTE_R1" --remote-speed-r2 "$REMOTE_R2" \
  --remote-separation "$REMOTE_SEP" \
  --reference-speed-r1 "$REF_R1" --reference-speed-r2 "$REF_R2" \
  --reference-separation "$REF_SEP" \
  --clock-pi-start "$RUN_DIR/pc/clock_pi_start.json" \
  --clock-pi-end "$RUN_DIR/pc/clock_pi_end.json" \
  --clock-mac-start "$RUN_DIR/pc/clock_mac_start.json" \
  --clock-mac-end "$RUN_DIR/pc/clock_mac_end.json" \
  --proc-pc "$RUN_DIR/pc/proc.csv" --proc-pi "$RUN_DIR/pi/proc.csv" \
  --proc-mac "$RUN_DIR/mac/proc.csv" \
  --runner-pi-log "$RUN_DIR/pi_reference/runner.log" \
  --runner-mac-log "$RUN_DIR/mac/runner.log" \
  --out "$RUN_DIR/metrics_e5.json" \
  || STATUS=1

trap - EXIT INT TERM
echo "E5 done (status=$STATUS): $RUN_DIR"
exit "$STATUS"
