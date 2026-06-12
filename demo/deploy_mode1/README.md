# Deploy mode 1 demo: all-in-one robot-side runtime

This mode runs the implemented monitor, converter and verdict pipeline inside
one `monitor_node` process on the robot host. The `/odom` topic owns its
DataRecord exporter, while the converter and verdict business rules live in
custom Python classes rather than YAML fields.

The Compose case is self-testing: it starts
`demo/common/robot_simulator.py` in the same container, monitors the robot's
`/odom` motion, and switches its speed every three seconds:

- `0.4 m/s`: above the `0.3 m/s` limit, emitting `result=false`
- `0.2 m/s`: below the limit, emitting a clearing `result=true`

The verdict service emits only when the property state changes, so the log
alternates between violation and recovery instead of printing at 10 Hz.

## Run

From the project root:

```bash
docker compose -f demo/deploy_mode1/docker-compose.yml up --build
```

The container uses `network_mode: host`, preserving the traditional
robot-side topology and allowing the bundled robot and monitor to share DDS.
No separately started ROS2 process is required.

DataRecords and verdicts are written under:

```text
output/mode1/
```
