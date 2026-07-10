# E3 — Nav2 single-robot safety supervision

Unmodified Nav2 (TB3 waffle) navigating the custom corridor world
(`my_nav2_worlds`) under a deterministic three-goal mission with scripted
obstacle spawns; monitor_node + node_runner split over MQTT (1884).
Properties: P1 commanded speed limit (oracle-checked), P2 navigation-goal
deadline (checked against the mission log). Full plan and results:
[../PLAN.md](../PLAN.md), section 6.

Run (headless reference):

```bash
eval/e3/run.sh
```

GUI run for thesis figures (Gazebo client + RViz):

```bash
HEADLESS=False USE_RVIZ=True eval/e3/run.sh
```

Outputs land in `eval/e3/results/run_<timestamp>/`: resolved configs,
records + verdict JSONL, `mission_log.json` (ground truth),
`metrics_speed.json`, `goals.json`, logs.
