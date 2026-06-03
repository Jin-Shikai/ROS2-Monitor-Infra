# Mode 2 demo: monitor node + MQTT broker + verdict runner

This demo runs the split architecture where the robot-side monitor only
collects ROS2 data and publishes DataRecords, while the verifier-side runner
subscribes to those DataRecords and evaluates converter/verdict chains.

Included services:

- `mosquitto`: transport broker on `127.0.0.1:1883`
- `monitor_node`: ROS2-facing collector and DataRecord MQTT publisher
- `verdict_runner`: MQTT DataRecord subscriber plus converter/verdict pipeline

The `/odom` topic owns its DataRecord exporter in `robot_config.yaml`.
Business choices such as source filtering, field selection and threshold are
owned by `custom.odom_speed_converter` and `custom.odom_speed_verdict`; the
verifier config only selects those classes and declares verdict outputs.

Admin UI, replay, feedback and evidence runtime are intentionally not part of
this demo yet.

## Run

From the project root:

```bash
docker compose -f demo/deploy_mode2/docker-compose.yml up --build
```

The compose uses `network_mode: host` so the monitor container can participate
in host DDS discovery and both Python processes can reach the broker at
`127.0.0.1:1883`.

## Feed it ROS2 data

Run any ROS2 node that publishes `/odom` with type `nav_msgs/msg/Odometry` on
the same host and `ROS_DOMAIN_ID=0`. The repo's fake robot is enough:

```bash
source /opt/ros/kilted/setup.bash
python3 test/fake_robot.py
```

The custom verdict class uses `speed > 0.3`, while `test/fake_robot.py`
publishes `/odom.twist.twist.linear.x = 0.4`, so the verifier should emit a
violation verdict soon after data starts flowing.

Verdicts are printed by `verdict_runner` and also written under:

```text
output/mode2/verifier/
```

## Config files

- `robot_config.yaml`: monitor-side config. It subscribes to `/odom`, extracts
  selected fields, and publishes DataRecords to MQTT.
- `verifier_config.yaml`: verifier-side config. It subscribes to MQTT
  DataRecords and runs the `RuleBasedConverter -> ThresholdVerdict` chain.
