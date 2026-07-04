# Shared demo robot

`robot_simulator.py` is deliberately small: it publishes only `/odom` and
`/cmd_vel`, and each scenario has fixed behavior. There are no behavior
configuration switches.

| Scenario | Repeating behavior |
|---|---|
| `speed-limit-cycle` | `/odom` speed alternates between `0.4` and `0.2 m/s` |
| `cmd-velocity-cycle` | `/cmd_vel` alternates between `1.85` and `0.2 m/s` |
| `stationary-origin` | Reference robot remains at `x=0.0 m` |
| `minimum-distance-cycle` | Robot alternates between `x=0.5` and `x=1.5 m` |

Every phase lasts three seconds. The robot logs each phase transition as an
input value only; converter and verdict components own all monitoring logic.

Example:

```bash
python3 demo/common/robot_simulator.py speed-limit-cycle
```

Multi-robot demos use standard ROS remapping arguments to assign node names and
namespaces.

## Service and action demos

The service/action demos are intentionally separate from the topic robot so each
ROS graph shape stays easy to inspect.

### Service

```bash
python3 demo/common/service_simulator.py
```

This exposes `/reset_pose` as `std_srvs/srv/Trigger` and calls it every three
seconds. The service enables ROS 2 service introspection when the active ROS
distro supports it, so a monitor configured for `/reset_pose` can observe
request/response records.

Dashboard container command:

```bash
source /opt/ros/kilted/setup.bash && python3 /demo/common/service_simulator.py --ros-args -r __node:=showcase_service_robot
```

### Action

```bash
python3 demo/common/action_simulator.py
```

This exposes `/demo_fibonacci` as `example_interfaces/action/Fibonacci` and
sends itself a small goal every five seconds, producing feedback and status
traffic.

Dashboard container command:

```bash
source /opt/ros/kilted/setup.bash && python3 /demo/common/action_simulator.py --ros-args -r __node:=showcase_action_robot
```
