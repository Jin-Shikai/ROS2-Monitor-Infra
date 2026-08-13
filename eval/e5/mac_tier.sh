#!/usr/bin/env bash
# macOS verifier tier for E5. The caller must keep its interactive SSH or
# local terminal session alive: macOS 15 Local Network privacy can deny LAN TCP
# after a detached process is orphaned from that session.
set -euo pipefail

cd "$(dirname "$0")/../.."
RUN_REL="${1:?usage: mac_tier.sh <remote-run-dir>}"
PYTHON_BIN="${E5_MAC_PYTHON:-/opt/homebrew/bin/python3.12}"
MAC_DIR="$RUN_REL/mac"
CONTROL="$RUN_REL/control"
mkdir -p "$MAC_DIR" "$CONTROL"
rm -f "$CONTROL/mac_ready"

export PYTHONPATH="$PWD:$PWD/monitor:${PYTHONPATH:-}"
export PYTHONUNBUFFERED=1

{
  # BSD date on macOS has no GNU -I flag.
  date '+%Y-%m-%dT%H:%M:%S%z'
  uname -a
  sw_vers
  echo "cores: $(sysctl -n hw.ncpu)"
  "$PYTHON_BIN" --version
  "$PYTHON_BIN" -c 'import paho.mqtt, yaml; print("paho_mqtt:", paho.mqtt.__version__); print("pyyaml:", yaml.__version__)'
  systemsetup -getusingnetworktime 2>/dev/null || true
  systemsetup -getnetworktimeserver 2>/dev/null || true
} > "$MAC_DIR/env.txt" 2>&1

RUNNER_PID=""
SAMPLER_PID=""

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

cleanup() {
  set +e
  stop_pid INT "$RUNNER_PID"
  wait_pid_bounded "$RUNNER_PID" 20
  stop_pid TERM "$SAMPLER_PID"
  wait_pid_bounded "$SAMPLER_PID" 5
}
trap cleanup EXIT INT TERM

"$PYTHON_BIN" monitor/node_runner.py -c "$RUN_REL/config/mac.yaml" \
  > "$MAC_DIR/runner.log" 2>&1 &
RUNNER_PID=$!

"$PYTHON_BIN" eval/common/ps_proc_sampler.py --pid "$RUNNER_PID" \
  --interval 1 --out "$MAC_DIR/proc.csv" &
SAMPLER_PID=$!

for _ in $(seq 1 45); do
  if grep -q "MQTTSource connected" "$MAC_DIR/runner.log" 2>/dev/null; then
    break
  fi
  kill -0 "$RUNNER_PID" 2>/dev/null || exit 1
  sleep 1
done
grep -q "MQTTSource connected" "$MAC_DIR/runner.log"
touch "$CONTROL/mac_ready"
echo "E5_MAC_READY"

while [ ! -e "$CONTROL/stop" ]; do
  kill -0 "$RUNNER_PID" 2>/dev/null
  sleep 1
done

cleanup
trap - EXIT INT TERM
echo "E5_MAC_DONE"
