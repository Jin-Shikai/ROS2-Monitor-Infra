# Split deployment — converter and verdict on different hosts

`deploy_mode2` splits **collector | converter+verdict** across two hosts. This
demo adds a further split **converter | verdict**, so three components run as
separate processes joined by MQTT:

```
robot host                converter host                 verdict host
  monitor_node  --monitor/#-->  split_runner  --dsl/odom_speed-->  split_runner
  (Collector +              (--role converter:             (--role verdict:
   Transformer)             converters publish              verdict stages
                            DSL records)                    consume them)
```

The seam is the converter's `dsl_transport:` block in `split_config.yaml` — the
MQTT topic the converter publishes DSL-ready records to and the verdict host
subscribes from. This is enabled by `build_converter_stage` /
`build_verdict_stage` in `monitor/pipeline.py` and the DSL-record transport in
`monitor/dsl_transport.py`.

Included services:

- `mosquitto`: transport broker on `127.0.0.1:1883`
- `monitor_node`: bundled scenario robot, ROS2 collector, DataRecord publisher
- `split_converter`: `split_runner --role converter` (publishes DSL records)
- `split_verdict`: `split_runner --role verdict` (emits verdicts)

## Run (self-testing)

From the project root:

```bash
docker compose -f demo/deploy_split_converter_verdict/docker-compose.yml up --build
```

The Compose case is self-testing: it starts the `speed-limit-cycle` scenario
inside `monitor_node` (no external ROS2 process required). The shared
`demo/common/robot_simulator.py` alternates `/odom` speed between `0.4` and
`0.2 m/s` around the custom limit `0.30`, so `split_verdict` repeatedly emits
`odom_speed_limit` violation and recovery. Verdicts are printed by
`split_verdict` and written under `output/split/verifier/`.

## Run manually (needs an MQTT broker on 127.0.0.1:1883)

```bash
# verdict host
python monitor/split_runner.py --role verdict   -c demo/deploy_split_converter_verdict/split_config.yaml
# converter host
python monitor/split_runner.py --role converter -c demo/deploy_split_converter_verdict/split_config.yaml
# robot host (publishes /odom DataRecords)
python monitor/monitor_node.py -c demo/deploy_split_converter_verdict/robot_config.yaml
```

## Config files

- `robot_config.yaml`: monitor-side; subscribes to `/odom`, extracts fields,
  publishes DataRecords to MQTT (`monitor/#`).
- `split_config.yaml`: shared by both `split_runner` roles. `--role converter`
  reads `verdict_runner.source` and each converter's `dsl_transport`;
  `--role verdict` reads each converter's `dsl_transport` and `verdict`. See
  `docs/config_spec.md` (`dsl_transport`, `split_runner`).
