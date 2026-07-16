# E4 — Multi-robot fleet property

Two namespaced TB3 + Nav2 stacks (`/robot1`, `/robot2`) in the custom
corridor world on deliberately crossing patrol routes (two legs, swapping
the corridor ends), brought up by `fleet_launch.py` — a reduction of the
stock `cloned_multi_tb3_simulation_launch.py` chain that starts exactly one
`/clock` bridge (the stock files start one per robot, and two `/clock`
publishers make subscribers observe time jumping backwards, aborting goals
at random). One monitor_node observes both namespaces; one node_runner
(MQTT, 1884) evaluates:

- P1a/P1b per-robot commanded speed limit on `/robotN/cmd_vel`
  (independent converter chains: namespace isolation is structural),
- P2 fleet minimum separation from both `/robotN/amcl_pose` streams
  (`custom.separation` — AMCL poses share the map frame, unlike the
  spawn-anchored per-robot `/odom` frames).

The robots are spawned from `gz_waffle_visible.sdf.xacro` — the stock
waffle plus a primitive visual crossing the lidar scan plane: two stock
waffles are mutually invisible (the scan plane passes above the sibling's
body), which lets them physically collide. Verdicts are validated against
the offline distance oracle (`check_separation.py`) and independently
against Gazebo's physical world poses (`gt_logger.py` + `check_gt.py`).

AMCL initial poses are published per robot on `/robotN/initialpose` by
`run.sh` during bringup (the shared Nav2 params file cannot carry two
poses). Full plan and results: [../PLAN.md](../PLAN.md), section 7.

`request.json` is the authoritative monitoring deployment description.
`run.sh` injects `RUN_DIR`, `SEP_MIN`, and `SPEED_MAX` with config_gen's typed
`--var` option and generates `monitor.yaml` plus `runner.yaml`. The `.yaml.in`
files are retained only as historical references.

Run (headless reference):

```bash
eval/e4/run.sh
```

Clean up a completed or interrupted E4 run before starting another one:

```bash
eval/e4/cleanup.sh
```

The cleanup covers E4 monitor / mission processes, the dedicated MQTT broker,
both Nav2 stacks, RViz, and Gazebo server / GUI, and verifies that TCP port
1884 is free. It also runs automatically before and after `run.sh`.

GUI run for thesis figures (per-robot RViz):

```bash
USE_RVIZ=True eval/e4/run.sh
```

Outputs land in `eval/e4/results/run_<timestamp>/`: resolved configs,
the copied generation request + `config_gen.log`, records + verdict JSONL,
`mission_log.json` (mission ground truth),
`gt_poses.csv` (simulator ground truth), `metrics_speed_r1.json`,
`metrics_speed_r2.json`, `separation.json`, `gt.json`, logs.
