#!/usr/bin/env bash
# Raspberry Pi tier for E5. The automated harness keeps it under a live SSH
# process; the manual wrapper keeps it in a foreground Pi terminal. Control
# markers provide ordered shutdown: stop_monitor -> monitor_stopped -> stop_all.
set -euo pipefail

cd "$(dirname "$0")/../.."
RUN_REL="${1:?usage: pi_tier.sh <remote-run-dir>}"
PI_DIR="$RUN_REL/pi"
REF_DIR="$RUN_REL/pi_reference"
CONTROL="$RUN_REL/control"
mkdir -p "$PI_DIR" "$REF_DIR" "$CONTROL"
rm -f "$CONTROL/pi_ready" "$CONTROL/monitor_stopped"

set +u
source /opt/ros/kilted/setup.bash
set -u
export PYTHONPATH="$PWD:$PWD/monitor:${PYTHONPATH:-}"
export PYTHONUNBUFFERED=1

{
  date -Is
  uname -a
  echo "cores: $(nproc)"
  python3 --version
  python3 -c 'import paho.mqtt; print("paho_mqtt:", paho.mqtt.__version__)'
  echo "ros_distro: ${ROS_DISTRO:-unknown}"
  echo "ros_domain_id: ${ROS_DOMAIN_ID:-0}"
  echo "rmw_implementation: ${RMW_IMPLEMENTATION:-default}"
  ip -brief address show eth0
  timedatectl status || true
} > "$PI_DIR/env.txt" 2>&1

BROKER_PID=""
RUNNER_PID=""
MON_PID=""
SAMPLER_PID=""
MONITOR_STOPPED=0

stop_pid() {
  local signal="$1"
  local pid="$2"
  [ -n "$pid" ] || return 0
  kill "-$signal" "$pid" 2>/dev/null || true
}

wait_pid_bounded() {
  local pid="$1"
  local limit="${2:-20}"
  local count=0
  [ -n "$pid" ] || return 0
  while kill -0 "$pid" 2>/dev/null && [ "$count" -lt "$limit" ]; do
    sleep 1
    count=$((count + 1))
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null || true
  fi
  wait "$pid" 2>/dev/null || true
}

stop_monitor() {
  [ "$MONITOR_STOPPED" -eq 0 ] || return 0
  stop_pid INT "$MON_PID"
  wait_pid_bounded "$MON_PID" 20
  MONITOR_STOPPED=1
  touch "$CONTROL/monitor_stopped"
}

cleanup() {
  set +e
  stop_monitor
  stop_pid TERM "$SAMPLER_PID"
  wait_pid_bounded "$SAMPLER_PID" 5
  stop_pid INT "$RUNNER_PID"
  wait_pid_bounded "$RUNNER_PID" 20
  stop_pid TERM "$BROKER_PID"
  wait_pid_bounded "$BROKER_PID" 10
}
trap cleanup EXIT INT TERM

mosquitto -c eval/e5/mosquitto.conf > "$PI_DIR/broker.log" 2>&1 &
BROKER_PID=$!
for _ in $(seq 1 30); do
  if ss -ltn 2>/dev/null | grep -qE ':[1]884[[:space:]]'; then
    break
  fi
  sleep 1
done
ss -ltn 2>/dev/null | grep -qE ':[1]884[[:space:]]' || {
  echo "E5 Pi: broker did not listen on port 1884" >&2
  exit 1
}

python3 monitor/node_runner.py -c "$RUN_REL/config/pi_reference.yaml" \
  > "$REF_DIR/runner.log" 2>&1 &
RUNNER_PID=$!

python3 monitor/monitor_node.py -c "$RUN_REL/config/pi.yaml" \
  > "$PI_DIR/monitor.log" 2>&1 &
MON_PID=$!

python3 eval/common/proc_sampler.py --pid "$MON_PID" --pid "$RUNNER_PID" \
  --interval 1 --out "$PI_DIR/proc.csv" &
SAMPLER_PID=$!

for _ in $(seq 1 30); do
  runner_connected=0
  broker_clients=0
  grep -q "MQTTSource connected" "$REF_DIR/runner.log" 2>/dev/null && runner_connected=1
  broker_clients="$(grep -c "New client connected" "$PI_DIR/broker.log" 2>/dev/null || true)"
  if [ "$runner_connected" -eq 1 ] && [ "$broker_clients" -ge 2 ]; then
    break
  fi
  kill -0 "$RUNNER_PID" 2>/dev/null && kill -0 "$MON_PID" 2>/dev/null || exit 1
  sleep 1
done
grep -q "MQTTSource connected" "$REF_DIR/runner.log"
[ "$(grep -c "New client connected" "$PI_DIR/broker.log" 2>/dev/null || true)" -ge 2 ]
touch "$CONTROL/pi_ready"
echo "E5_PI_READY"

while [ ! -e "$CONTROL/stop_monitor" ]; do
  kill -0 "$BROKER_PID" 2>/dev/null
  kill -0 "$RUNNER_PID" 2>/dev/null
  kill -0 "$MON_PID" 2>/dev/null
  sleep 1
done
stop_monitor

while [ ! -e "$CONTROL/stop_all" ]; do
  kill -0 "$BROKER_PID" 2>/dev/null
  kill -0 "$RUNNER_PID" 2>/dev/null
  sleep 1
done

cleanup
trap - EXIT INT TERM
echo "E5_PI_DONE"
