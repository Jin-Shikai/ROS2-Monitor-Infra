# E2 — Distribution transparency and observable breadth

Single host, three tiers: stimulus robots -> monitor_node --MQTT(1884)-->
node_runner. The speed property runs both in-process and remotely and the
two verdict streams are diffed (`transparency.json`); the reset-pose
service-effect property and a Fibonacci action exercise service and action
monitoring. Full plan and results: [../PLAN.md](../PLAN.md), section 5.

`request.json` describes both deployment hosts and their MQTT records link.
`run.sh` projects it with `monitor/config_gen.py` into `monitor.yaml` and
`runner.yaml`; the `.yaml.in` files are historical references, not inputs.

Run:

```bash
eval/e2/run.sh [duration_seconds]   # default 60
```

`run.sh` automatically performs bounded shutdown and frees the dedicated
MQTT port. After an interrupted run, it can also be invoked explicitly:

```bash
eval/e2/cleanup.sh
```

Outputs land in `eval/e2/results/run_<timestamp>/`: resolved configs,
the generation request + `config_gen.log`, records + verdict JSONL (local /
remote / reset), broker and node logs, `metrics_speed_remote.json`,
`transparency.json`, `extras.json`.
