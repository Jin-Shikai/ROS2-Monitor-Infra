# E2 — Distribution transparency and observable breadth

Single host, three tiers: stimulus robots -> monitor_node --MQTT(1884)-->
node_runner. The speed property runs both in-process and remotely and the
two verdict streams are diffed (`transparency.json`); the reset-pose
service-effect property and a Fibonacci action exercise service and action
monitoring. Full plan and results: [../PLAN.md](../PLAN.md), section 5.

Run:

```bash
eval/e2/run.sh [duration_seconds]   # default 60
```

Outputs land in `eval/e2/results/run_<timestamp>/`: resolved configs,
records + verdict JSONL (local / remote / reset), broker and node logs,
`metrics_speed_remote.json`, `transparency.json`, `extras.json`.
