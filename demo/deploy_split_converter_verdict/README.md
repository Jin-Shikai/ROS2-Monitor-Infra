# Split deployment — converter and verdict on different hosts

`deploy_mode2` splits **collector | converter+verdict** across two hosts. This
demo adds a further split **converter | verdict**, so three components run as
separate processes joined by MQTT:

```
robot host                converter host                 verdict host
  monitor_node  --monitor/#-->  node_runner  --dsl/odom_speed-->  node_runner
  (Collector +              (records input ->              (dsl input ->
   Transformer)              converter ->                   verdict service ->
                             dsl output)                    verdict exporters)
```

The seam is a dsl transport endpoint: the converter host declares an
`outputs:` entry and the verdict host declares an `inputs:` entry naming the
same MQTT topic. Both hosts run the same `monitor/node_runner.py` entrypoint —
what a host does is decided entirely by its YAML, not by a per-process role.

Included services:

- `mosquitto`: transport broker on `127.0.0.1:1883`
- `monitor_node`: bundled scenario robot, ROS2 collector, DataRecord publisher
- `converter_host`: node_runner consuming records, publishing DSL records
- `verdict_host`: node_runner consuming DSL records, emitting verdicts

## Run (self-testing)

From the project root:

```bash
docker compose -f demo/deploy_split_converter_verdict/docker-compose.yml up --build
```

The Compose case is self-testing: it starts the `speed-limit-cycle` scenario
inside `monitor_node` (no external ROS2 process required). The shared
`demo/common/robot_simulator.py` alternates `/odom` speed between `0.4` and
`0.2 m/s` around the custom limit `0.30`. The robot only publishes values;
`verdict_host` owns the `odom_speed_limit` violation and recovery verdicts.
Verdicts are printed by `verdict_host` and written under
`output/split/verifier/`.

## Run manually (needs an MQTT broker on 127.0.0.1:1883)

```bash
# verdict host
python monitor/node_runner.py -c demo/deploy_split_converter_verdict/verdict_config.yaml
# converter host
python monitor/node_runner.py -c demo/deploy_split_converter_verdict/converter_config.yaml
# robot host (publishes /odom DataRecords)
python monitor/monitor_node.py -c demo/deploy_split_converter_verdict/robot_config.yaml
```

## Config files

- `robot_config.yaml`: monitor-side; subscribes to `/odom`, extracts fields,
  publishes DataRecords to MQTT (`monitor/#`).
- `converter_config.yaml`: records `inputs:` entry + converter + dsl
  `outputs:` entry on topic `dsl/odom_speed`.
- `verdict_config.yaml`: dsl `inputs:` entry on the same topic + verdict
  service + verdict exporters. See `docs/config_spec.md` (`inputs`, `outputs`,
  `links`).
