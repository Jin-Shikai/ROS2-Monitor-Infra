# Deploy mode 1 demo: all-in-one robot-side runtime

This mode runs the implemented monitor, converter and verdict pipeline inside
one `monitor_node` process on the robot host. The `/odom` topic owns its
DataRecord exporter, while the converter and verdict business rules live in
custom Python classes rather than YAML fields.

Not included yet: replay, feedback, evidence runtime and dashboard.

## Run

From the project root:

```bash
docker compose -f demo/deploy_mode1/docker-compose.yml up --build
```

The container uses `network_mode: host` so ROS2 DDS discovery can see robot
nodes on the host. Use `ROS_DOMAIN_ID=0` for the robot process.

## Feed it ROS2 data

Run a ROS2 node publishing `/odom` as `nav_msgs/msg/Odometry`, for example:

```bash
source /opt/ros/kilted/setup.bash
python3 test/fake_robot.py
```

DataRecords and verdicts are written under:

```text
output/mode1/
```
