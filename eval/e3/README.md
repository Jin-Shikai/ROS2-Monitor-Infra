# E3 — Nav2 single-robot safety supervision

Unmodified Nav2 (TB3 waffle) navigating the custom corridor world
(`my_nav2_worlds`) under a deterministic three-goal mission with scripted
route-closing obstacle spawns; monitor_node + node_runner split over MQTT
(1884). Goal A uses the normal lower opening in the right partition; before
goal B that complete opening is closed to force the upper route; before goal
C the remaining upper opening is also closed, disconnecting the two sides.
Properties: P1 commanded speed limit (oracle-checked), P2 navigation-goal
deadline (checked against the mission log). The Gazebo ground-truth pose is
also logged independently, so the configured initial pose and every
successful physical endpoint are checked against the mission's map-frame
coordinates. Full plan and results:
[../PLAN.md](../PLAN.md), section 6.

`request.json` is projected at startup into the monitor and runner YAML. The
`DEADLINE` environment value is injected through config_gen's typed
`--var DEADLINE=...` substitution, so the generated converter parameter is a
number. The `.yaml.in` files remain only as historical references.

Run (headless reference):

```bash
eval/e3/run.sh
```

Useful overrides are `DEADLINE=45`, `CANCEL_AFTER=120`, and
`GOAL_TOLERANCE=0.5` (metres). `run.sh` cleans stale E3/Nav2/Gazebo processes
before and after each run. To clean an interrupted run manually:

```bash
eval/e3/cleanup.sh
```

GUI run for thesis figures (Gazebo client + RViz):

```bash
HEADLESS=False USE_RVIZ=True eval/e3/run.sh
```

Outputs land in `eval/e3/results/run_<timestamp>/`: resolved configs,
`request.json`, `config_gen.log`, records + verdict JSONL, `mission_log.json`,
`gt_poses.csv` (Gazebo truth), `metrics_speed.json`, `goals.json`,
`physical_poses.json`, `routes.json`, logs.
