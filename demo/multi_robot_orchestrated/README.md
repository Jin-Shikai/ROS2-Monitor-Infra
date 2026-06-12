# Multi-robot orchestrated monitoring

Two robot-side monitor locations publish namespaced traces to one MQTT broker.
A central verifier evaluates one isolated property chain per robot.

```bash
docker compose -f demo/multi_robot_orchestrated/docker-compose.yml up --build
```

Both robots run `speed-limit-cycle`. Expected result: separate `robot1_speed`
and `robot2_speed` violation/recovery cycles at the central verifier.
