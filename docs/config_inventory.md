# Configuration Inventory and Documentation Audit

> Audit date: 2026-06-15

## Result

Before this audit, [config_spec.md](config_spec.md) documented most framework
fields, but the documentation did **not fully satisfy** the requirement that
every configurable field have documented values and meaning:

- the concrete configuration files were not inventoried;
- several fields had a type but no supported-value or validity constraints;
- constructor arguments of the project-shipped `custom.*` plugins were absent;
- DSL adaptation previously existed only inside a long design note;
- no algorithm described how runtime YAML could be generated.

After this audit, the documentation set is:

| Requirement | Normative document |
|---|---|
| Runtime YAML fields and built-in plugin fields | [config_spec.md](config_spec.md) |
| Concrete file inventory and project custom plugin fields | this document |
| New DSL adaptation procedure | [dsl_adaptation_guide.md](dsl_adaptation_guide.md) |
| Configuration-generation algorithm and pseudocode | [config_generation_algorithm.tex](config_generation_algorithm.tex) (algorithm); `monitor/config_gen.py` (implementation) |

## Scope

The application accepts one project-owned configuration language: the runtime
YAML parsed by `MonitorConfig` or `RunnerConfig` in
`monitor/config_model.py`. All `monitor/config.yaml` and demo `*.yaml` files
listed below use this language and are covered field-by-field by
[config_spec.md](config_spec.md) plus the custom-plugin tables below.

The following are configurable files used to launch demos, but are owned by
external tools rather than parsed by ROS2-Monitor-Infra:

| File kind | Owner/schema | Purpose |
|---|---|---|
| root and `demo/*/docker-compose.yml` | Docker Compose Specification | Container topology, mounts, networks, commands, and environment. |
| `demo/deploy_mode2/mosquitto.conf`, `demo/deploy_mode3/mosquitto.conf` | Eclipse Mosquitto | Demo MQTT listener and anonymous-access settings. |
| `Dockerfile` | Dockerfile syntax | Builds the common ROS2 demo image. |
| `pyproject.toml` | Python packaging/pytest | Python dependency and test configuration. |

These external formats are intentionally not re-specified field-by-field here.
Their values are deployment inputs, not fields of the monitoring configuration
generation algorithm.

## Runtime YAML Inventory

All files in this table use the schema in [config_spec.md](config_spec.md).

| Files | Runtime role |
|---|---|
| `monitor/config.yaml` | Full reference example containing monitor-side and verifier-side sections. |
| `demo/deploy_mode1/config.yaml` | Integrated local monitor and verdict evaluation. |
| `demo/deploy_mode2/robot_config.yaml` | Robot-side collection and MQTT export using host networking. |
| `demo/deploy_mode2/verifier_config.yaml` | Central MQTT ingestion and verdict evaluation using host networking. |
| `demo/deploy_split_converter_verdict/robot_config.yaml` | Robot-side collection and MQTT export for the three-host converter/verdict split. |
| `demo/deploy_split_converter_verdict/converter_config.yaml` | Converter-host `node_runner` config: records input, converter, dsl output. |
| `demo/deploy_split_converter_verdict/verdict_config.yaml` | Verdict-host `node_runner` config: dsl input routed to the verdict service. |
| `demo/deploy_mode3/robot_config.yaml` | Robot-side collection and MQTT export through a published broker port. |
| `demo/deploy_mode3/verifier_config.yaml` | Central MQTT ingestion and verdict evaluation through the Compose network. |
| `demo/deploy_mode4_hybrid/robot_config.yaml` | Hybrid deployment's robot-side local evaluation and raw export. |
| `demo/deploy_mode4_hybrid/verifier_config.yaml` | Hybrid deployment's central evaluation. |
| `demo/nav2_compatible_local/config.yaml` | Self-contained local monitoring of Nav2-compatible topics. |
| `demo/nav2_compatible_local/full_nav2_config.yaml` | Broader template for a full Nav2 graph. |
| `demo/multi_robot_orchestrated/robot1.yaml` | First robot's raw-record exporter. |
| `demo/multi_robot_orchestrated/robot2.yaml` | Second robot's raw-record exporter. |
| `demo/multi_robot_orchestrated/verifier.yaml` | Central per-robot property evaluation. |
| `demo/multi_robot_global/robot1.yaml` | First robot's position-record exporter. |
| `demo/multi_robot_global/robot2.yaml` | Second robot's position-record exporter. |
| `demo/multi_robot_global/verifier.yaml` | Central cross-robot distance property. |
| `demo/choreographed_verdicts/robot1.yaml` | First robot's local property and verdict export. |
| `demo/choreographed_verdicts/robot2.yaml` | Second robot's local property and verdict export. |
| `demo/choreographed_verdicts/aggregator.yaml` | Central aggregation of local verdicts. |
| `demo/offline_replay/recorder.yaml` | Live DataRecord recording. |
| `demo/offline_replay/config.yaml` | File replay and verdict evaluation. |

## Project-Shipped Custom Plugin Fields

For every plugin block, `type` is required and must equal the exact value in
the table. Fields not listed for that class are passed to its Python
constructor and therefore cause a constructor error unless the class accepts
them. A constructor error causes that chain to be skipped.

### Converters

| `type` | Field | Type / allowed values | Required | Default | Meaning |
|---|---|---|---:|---|---|
| `custom.speed:CmdVelSpeedConverter` | none | - | - | - | Extracts `linear.x` from command velocity records as `speed`. |
| `custom.fleet_distance:FleetDistanceConverter` | `robot_a` | ROS namespace string | yes | none | First robot namespace; trailing slash is removed. |
| same | `robot_b` | ROS namespace string | yes | none | Second robot namespace; trailing slash is removed. |
| `custom.relative_speed:RelativeSpeedConverter` | `robot_a` | ROS namespace string | no | inferred from first `<robot>/odom` input | First robot namespace; joins `<robot>/odom` streams. |
| same | `robot_b` | ROS namespace string | no | inferred from second `<robot>/odom` input | Second robot namespace. |
| same | `components` | list of dot-path strings | no | odom planar velocity | Velocity components compared between the robots. |
| same | `property_id` | string | no | `fleet_relative_speed` | `_property_id` tag on emitted records. |
| `custom.stale_watchdog:StaleWatchdogConverter` | `timeout_sec` | number `> 0` | yes | none | Silence duration after which the watchdog emits; uses the converter lifecycle (`start`/`stop`) with its own timer thread. |
| same | `property_id` | string | no | `source_liveness` | `_property_id` tag on emitted records. |
| same | `check_interval_sec` | number `> 0` | no | `timeout_sec / 4` | Timer poll interval. |
| `custom.verdict_aggregation:LocalViolationCountConverter` | none | - | - | - | Counts currently violating local-verdict sources. |
| `custom.odom_speed_converter:OdomSpeedConverter` | none | - | - | - | Fixed demo converter for `/odom` and `twist.twist.linear.x`. |
| `custom.nav2_case1.cmd_vel_speed_converter:CmdVelSpeedConverter` | none | - | - | - | Extracts `twist.linear.x`; normally paired with `inputs: ["/cmd_vel"]`. |
| `custom.cmd_vel_speed:Demo1VelocityConverter` | `speed_path` | dot-path string | no | `linear.x` | Demo dashboard converter field to read. |
| same | `output_field` | string | no | `speed` | DSL record key to write. |

### Verdict Services

| `type` | Field | Type / allowed values | Required | Default | Meaning |
|---|---|---|---:|---|---|
| `custom.threshold:ThresholdVerdict` | `threshold` | number convertible to float | no | `0.3` | Violation occurs when the first numeric DSL payload value is greater than this value. |
| same | `property_id` | string | no | DSL `_property_id` or compared field name | Identifier written into every emitted verdict. |
| `custom.fleet_distance:MinimumFleetDistanceVerdict` | `minimum_distance` | number convertible to float | no | `1.0` | Violation occurs when computed distance is below this value. |
| `custom.verdict_aggregation:SimultaneousLocalViolationsVerdict` | `minimum_count` | integer; `>= 1` recommended | no | `2` | Violation occurs when at least this many local sources violate. |
| `custom.odom_speed_verdict:OdomSpeedVerdict` | none | - | - | - | Fixed demo limit: `/odom` speed greater than `0.30 m/s`. |
| `custom.nav2_case1.cmd_vel_speed_verdict:CmdVelSpeedVerdict` | none | - | - | - | Fixed demo limit: command speed greater than `0.30 m/s`. |

### Custom Sources

| `type` | Fields | Meaning |
|---|---|---|
| `custom.verdict_mqtt_source:VerdictMQTTSource` | Same fields and allowed values as built-in `mqtt` source | Parses MQTT payloads as Verdict JSON and wraps them as `DataRecord` objects for aggregation. |

## Known Documentation and Validation Limits

- Plugin-specific fields are open-ended by design because
  `module.path:ClassName` can reference arbitrary user code. The complete
  authority for a third-party plugin is its constructor and its own
  documentation.
- The loader currently performs little schema validation. Several invalid
  values are accepted during YAML parsing and fail only while components are
  constructed or started.
- `monitor.session_id_prefix` may appear in a verifier-only file, but
  `RunnerConfig` ignores it and `node_runner` generates its own session id.
- `actions[*].phases` silently ignores unsupported strings.
- The generation algorithm's core projection is implemented in
  `monitor/config_gen.py`: it maps a deployment JSON request (hosts / runtimes /
  links) onto the runtime YAML parsed by `MonitorConfig` / `RunnerConfig`.
  Dashboard plugin metadata is described by the machine-readable manifests under
  `custom/manifests/`; generated runtime YAML still carries explicit class paths
  and constructor arguments for reproducibility.
