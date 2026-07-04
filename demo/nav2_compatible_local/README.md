# Nav2-compatible local monitoring

Runs a robot publisher and monitor at the same robot-side location. The
publisher exposes Nav2-relevant `/odom` and `/cmd_vel` interfaces; the monitor
checks a `/cmd_vel` speed property locally.

This is intentionally lighter than a full Nav2 simulation so it runs headless
on Docker Desktop. The same monitor config can observe a real Nav2 deployment.
For a broader real-Nav2 setup including `/amcl_pose`, `/plan`, and
`/navigate_to_pose`, use `full_nav2_config.yaml` as a starting point.

```bash
docker compose -f demo/nav2_compatible_local/docker-compose.yml up --build
```

The `cmd-velocity-cycle` scenario alternates `/cmd_vel` between `1.85` and
`0.2 m/s` every three seconds. The robot only publishes values; expected
monitor result: repeating
`nav2_cmd_vel_speed_limit` violation and recovery verdicts in stdout and
`output/nav2_compatible_local/verdicts_*.jsonl`.
