# Self-contained offline trace replay

This two-stage case starts the `speed-limit-cycle` scenario and a robot-side monitor that
records `/odom` DataRecords to `output/offline_replay/recorded_live.jsonl`.
After the recording becomes non-empty, a separate offline verifier replays it
through the same verdict pipeline used by online deployments.

```bash
docker compose -f demo/offline_replay/docker-compose.yml up --build
```

The replay source loops over the growing recording. Expected result: repeating
`odom_speed_limit` violation and recovery verdicts derived from the freshly
recorded robot motion.
