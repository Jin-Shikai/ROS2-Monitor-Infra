# Central global multi-robot predicate

Two robot traces are aggregated centrally. The verifier checks the global
predicate `distance(robot1, robot2) >= 1.0m`.

```bash
docker compose -f demo/multi_robot_global/docker-compose.yml up --build
```

Robot 1 remains at the origin. Robot 2 alternates between `0.5 m` and `1.5 m`
from it every three seconds. Expected result: repeating
`fleet_minimum_distance` violation and recovery verdicts.
