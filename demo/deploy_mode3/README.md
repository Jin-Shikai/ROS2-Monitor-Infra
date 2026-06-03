# Deploy mode 3 demo: split robot and verifier with brokered records/verdicts

This mode keeps the robot-side monitor in host networking for ROS2 DDS, but
runs the broker and verifier side as separate compose services. The monitor
publishes DataRecords to the broker through the host-published MQTT port; the
verifier consumes DataRecords from the broker and publishes verdicts back to a
separate MQTT topic.

Implemented in this demo:

- robot-side `monitor_node`
- MQTT transport broker
- verifier-side `verdict_runner`
- verdict output to stdout, file and MQTT

The robot config uses a per-topic DataRecord exporter under `/odom`. Business
choices such as source filtering, field selection and threshold are owned by
the custom converter/verdict classes, not by YAML.

Not included yet: evidence runtime, replay service, feedback adapter and
dashboard.

## Run

From the project root:

```bash
docker compose -f demo/deploy_mode3/docker-compose.yml up --build
```

## Feed it ROS2 data

Run a ROS2 node publishing `/odom` as `nav_msgs/msg/Odometry` with
`ROS_DOMAIN_ID=0`, for example:

```bash
source /opt/ros/kilted/setup.bash
python3 test/fake_robot.py
```

The verifier writes verdict files under:

```text
output/mode3/verifier/
```

MQTT topics used by the demo:

```text
monitor/#                         DataRecords from monitor_node
verdicts/robot1/odom_speed_limit  Verdicts from verdict_runner
```
