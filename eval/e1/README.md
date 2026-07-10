# E1 — Local correctness baseline

Single host, no MQTT: demo stimulus robot -> monitor_node with in-process
converter + verdict. Establishes the correctness reference and intrinsic
latency floor. Full plan and results: [../PLAN.md](../PLAN.md), section 4.

Run:

```bash
eval/e1/run.sh [duration_seconds]   # default 60
```

Outputs land in `eval/e1/results/run_<timestamp>/`:
`monitor.yaml` (resolved config), records + verdict JSONL, `monitor_proc.csv`,
logs, `env.txt`, and computed `metrics.json`.
