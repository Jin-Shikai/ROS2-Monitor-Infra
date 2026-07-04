# Mode 2 demo: monitor node + MQTT broker + node runner

This demo runs the split architecture where the robot-side monitor only
collects ROS2 data and publishes DataRecords, while the verifier-side runner
subscribes to those DataRecords and evaluates converter/verdict chains.

Included services:

- `mosquitto`: transport broker on `127.0.0.1:1883`
- `monitor_node`: bundled scenario robot, ROS2-facing collector, and DataRecord
  MQTT publisher
- `node_runner`: MQTT DataRecord subscriber plus converter/verdict graph

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

The Compose case is self-testing. It starts the `speed-limit-cycle` scenario
inside `monitor_node`, so no external ROS2 process is required. Host networking keeps
the intended split-host experiment shape and lets both Python processes reach
the broker at `127.0.0.1:1883`.

The custom verdict class uses `speed > 0.3`, while the shared
`demo/common/robot_simulator.py` alternates `/odom` speed between `0.4` and
`0.2 m/s`. The robot only publishes values; the central verifier owns the
violation/recovery verdicts.

Verdicts are printed by `node_runner` and also written under:

```text
output/mode2/verifier/
```

## Config files

- `robot_config.yaml`: monitor-side config. It subscribes to `/odom`, extracts
  selected fields, and publishes DataRecords to MQTT.
- `verifier_config.yaml`: verifier-side config. Its `inputs:` entry subscribes
  to MQTT DataRecords; the graph links the converter to the verdict service.
