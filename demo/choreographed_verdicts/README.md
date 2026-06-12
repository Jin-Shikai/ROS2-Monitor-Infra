# Choreographed local-verdict aggregation prototype

Each robot evaluates a local speed property. Only local verdicts are sent to
the aggregator, which emits a fleet-level verdict when two local violations
are active simultaneously.

```bash
docker compose -f demo/choreographed_verdicts/docker-compose.yml up --build
```

Both robots run the same speed violation/recovery cycle. Expected result: two
local verdict streams and a repeating `simultaneous_local_violations`
violation/recovery cycle at the aggregator.
