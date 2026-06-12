# Shared demo robot

`robot_simulator.py` is deliberately small: it publishes only `/odom` and
`/cmd_vel`, and each scenario has fixed behavior. There are no behavior
configuration switches.

| Scenario | Repeating behavior |
|---|---|
| `speed-limit-cycle` | `/odom` speed alternates between violating `0.4` and clear `0.2 m/s` |
| `cmd-velocity-cycle` | `/cmd_vel` alternates between violating `0.45` and clear `0.2 m/s` |
| `stationary-origin` | Reference robot remains at `x=0.0 m` |
| `minimum-distance-cycle` | Robot alternates between `x=0.5` and `x=1.5 m` |

Every phase lasts three seconds. The robot logs each phase transition, so a
demo's input behavior remains visible alongside its verdicts.

Example:

```bash
python3 demo/common/robot_simulator.py speed-limit-cycle
```

Multi-robot demos use standard ROS remapping arguments to assign node names and
namespaces.
