# Hybrid local and central verification

The robot-side monitor evaluates the speed property locally and also publishes
the same DataRecords over MQTT to a central verifier.

```bash
docker compose -f demo/deploy_mode4_hybrid/docker-compose.yml up --build
```

The `speed-limit-cycle` scenario alternates `/odom` speed every three seconds.
Expected result: matching violation and recovery verdicts continue to appear
in both `robot_and_monitor` and `central_verifier` logs.
