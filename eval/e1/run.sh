#!/usr/bin/env bash
# E1 — Local correctness baseline.
# Usage: eval/e1/run.sh [duration_seconds]   (default 60)
#
# Launches the demo stimulus robot and monitor_node (in-process evaluation),
# samples the monitor's CPU/RSS, stops everything after the given duration,
# and computes metrics.json from the recorded JSONL files.
set -euo pipefail

cd "$(dirname "$0")/../.."
DURATION="${1:-60}"
RUN_DIR="eval/e1/results/run_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUN_DIR"

{
  date -Is
  uname -a
  echo "cores: $(nproc)"
  python3 --version
  echo "ros_distro: ${ROS_DISTRO:-unknown}"
  echo "rmw: ${RMW_IMPLEMENTATION:-default}"
} > "$RUN_DIR/env.txt"

sed "s|@RUN_DIR@|$RUN_DIR|" eval/e1/monitor.yaml.in > "$RUN_DIR/monitor.yaml"

python3 demo/common/topic_robot.py cmd-velocity-cycle \
  > "$RUN_DIR/robot.log" 2>&1 &
ROBOT_PID=$!

python3 monitor/monitor_node.py -c "$RUN_DIR/monitor.yaml" \
  > "$RUN_DIR/monitor.log" 2>&1 &
MON_PID=$!

python3 eval/common/proc_sampler.py --pid "$MON_PID" --interval 1 \
  --out "$RUN_DIR/monitor_proc.csv" &
SAMPLER_PID=$!

cleanup() {
  kill -INT "$MON_PID" "$ROBOT_PID" 2>/dev/null || true
  kill "$SAMPLER_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "E1 running for ${DURATION}s (results: $RUN_DIR)"
sleep "$DURATION"

# Graceful stop: SIGINT lets monitor_node emit session_end and flush files.
kill -INT "$MON_PID" 2>/dev/null || true
wait "$MON_PID" 2>/dev/null || true
kill -INT "$ROBOT_PID" 2>/dev/null || true
wait "$ROBOT_PID" 2>/dev/null || true
wait "$SAMPLER_PID" 2>/dev/null || true
trap - EXIT

RECORDS=$(ls -t "$RUN_DIR"/e1_*.jsonl | grep -v verdicts_ | head -1)
VERDICTS=$(ls -t "$RUN_DIR"/verdicts_e1_*.jsonl | head -1)

python3 eval/common/analyze_run.py \
  --records "$RECORDS" \
  --verdicts "$VERDICTS" \
  --field linear.x --threshold 0.5 --source /cmd_vel \
  --proc "$RUN_DIR/monitor_proc.csv" \
  --out "$RUN_DIR/metrics.json"

echo "E1 done: $RUN_DIR/metrics.json"
