# Shared Demo Robots

## `topic_robot.py`

Publishes `/odom` and `/cmd_vel`. Each phase lasts three seconds.

| Scenario | Behavior |
|---|---|
| `speed-limit-cycle` | `/odom` speed alternates between `0.4` and `0.2 m/s`. |
| `cmd-velocity-cycle` | `/cmd_vel.linear.x` alternates between `1.85` and `0.2 m/s`. |
| `stationary-origin` | Robot remains at `x=0.0 m`. |
| `minimum-distance-cycle` | Robot alternates between `x=0.5` and `x=1.5 m`. |

Two-robot presets use normal ROS remapping, for example:

```bash
python3 demo/common/topic_robot.py speed-limit-cycle --ros-args -r __ns:=/robot1
```

## `reset_robot.py`

Publishes `/odom`, exposes `std_srvs/srv/Trigger` at `/reset_pose`, enables
service introspection, and calls the service every three seconds.

Odd calls reset odom near the origin; even calls report success but do not
reset. This gives the reset-service-effect preset both passing and failing
verdicts.
