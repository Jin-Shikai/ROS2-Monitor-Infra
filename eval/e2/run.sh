#!/usr/bin/env bash
# E2 — Distribution transparency and observable breadth.
# Usage: eval/e2/run.sh [duration_seconds]   (default 60)
#
# Topology (single host, three tiers):
#   stimulus robots --DDS--> monitor_node --MQTT(1884)--> node_runner
# The speed property is evaluated BOTH in-process (monitor) and remotely
# (runner); the two verdict streams are diffed for distribution transparency.
set -euo pipefail

cd "$(dirname "$0")/../.."
DURATION="${1:-60}"
RUN_DIR="eval/e2/results/run_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUN_DIR"

{
  date -Is
  uname -a
  echo "cores: $(nproc)"
  python3 --version
  echo "ros_distro: ${ROS_DISTRO:-unknown}"
  { mosquitto -h 2>&1 || true; } | head -1
} > "$RUN_DIR/env.txt"

sed "s|@RUN_DIR@|$RUN_DIR|" eval/e2/monitor.yaml.in > "$RUN_DIR/monitor.yaml"
sed "s|@RUN_DIR@|$RUN_DIR|" eval/e2/runner.yaml.in > "$RUN_DIR/runner.yaml"

mosquitto -c eval/e2/mosquitto.conf > "$RUN_DIR/broker.log" 2>&1 &
BROKER_PID=$!
sleep 1

python3 monitor/node_runner.py -c "$RUN_DIR/runner.yaml" \
  > "$RUN_DIR/runner.log" 2>&1 &
RUNNER_PID=$!

python3 monitor/monitor_node.py -c "$RUN_DIR/monitor.yaml" \
  > "$RUN_DIR/monitor.log" 2>&1 &
MON_PID=$!
sleep 2   # let monitor finish DDS discovery before the stimuli start

# topic_robot also publishes an /odom stream (always at the origin), which
# would corrupt the reset-effect correlation with reset_robot's /odom —
# remap it to an unmonitored name so /odom carries only reset_robot data.
python3 demo/common/topic_robot.py cmd-velocity-cycle \
  --ros-args -r odom:=/speed_odom \
  > "$RUN_DIR/topic_robot.log" 2>&1 &
TOPIC_PID=$!
python3 demo/common/reset_robot.py \
  > "$RUN_DIR/reset_robot.log" 2>&1 &
RESET_PID=$!
python3 eval/e2/action_robot.py --order 6 --period 5.0 \
  > "$RUN_DIR/action_robot.log" 2>&1 &
ACTION_PID=$!

python3 eval/common/proc_sampler.py --pid "$MON_PID" --pid "$RUNNER_PID" \
  --interval 1 --out "$RUN_DIR/proc.csv" &
SAMPLER_PID=$!

cleanup() {
  kill -INT "$TOPIC_PID" "$RESET_PID" "$ACTION_PID" \
    "$MON_PID" "$RUNNER_PID" 2>/dev/null || true
  kill "$SAMPLER_PID" "$BROKER_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "E2 running for ${DURATION}s (results: $RUN_DIR)"
sleep "$DURATION"

# Ordered shutdown so no records are in flight when a tier stops:
# stimuli first, then monitor (flushes session_end over MQTT), then runner.
kill -INT "$TOPIC_PID" "$RESET_PID" "$ACTION_PID" 2>/dev/null || true
wait "$TOPIC_PID" "$RESET_PID" "$ACTION_PID" 2>/dev/null || true
sleep 2
kill -INT "$MON_PID" 2>/dev/null || true
wait "$MON_PID" 2>/dev/null || true
sleep 2
kill -INT "$RUNNER_PID" 2>/dev/null || true
wait "$RUNNER_PID" 2>/dev/null || true
wait "$SAMPLER_PID" 2>/dev/null || true
kill "$BROKER_PID" 2>/dev/null || true
trap - EXIT

RECORDS=$(ls -t "$RUN_DIR"/e2mon_*.jsonl | grep -v verdicts_ | head -1)
LOCAL=$(ls -t "$RUN_DIR"/verdicts_local_*.jsonl | head -1)
REMOTE=$(ls -t "$RUN_DIR"/verdicts_remote_*.jsonl | head -1)
RESET=$(ls -t "$RUN_DIR"/verdicts_reset_*.jsonl | head -1)

STATUS=0

# Remote speed verdicts vs. offline oracle on monitor-side records
# (+ MQTT-hop detection latency as a secondary observation).
python3 eval/common/analyze_run.py \
  --records "$RECORDS" --verdicts "$REMOTE" \
  --field linear.x --threshold 0.5 --source /cmd_vel \
  --out "$RUN_DIR/metrics_speed_remote.json" || STATUS=1

# Distribution transparency: local vs. remote verdict streams.
python3 eval/common/compare_verdicts.py \
  --a "$LOCAL" --b "$REMOTE" \
  --out "$RUN_DIR/transparency.json" || STATUS=1

# Service-effect pattern + action-record ground truth.
python3 eval/e2/check_extras.py \
  --records "$RECORDS" --reset-verdicts "$RESET" \
  --action-log "$RUN_DIR/action_robot.log" --order 6 \
  --out "$RUN_DIR/extras.json" || STATUS=1

echo "E2 done (status=$STATUS): $RUN_DIR"
exit "$STATUS"
