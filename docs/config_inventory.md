# Configuration Inventory and Documentation Audit

> Audit date: 2026-06-15

## Result

Before this audit, [config_spec.md](config_spec.md) documented most framework
fields, but the documentation did **not fully satisfy** the requirement that
every configurable field have documented values and meaning:

- the concrete configuration files were not inventoried;
- several fields had a type but no supported-value or validity constraints;
- constructor arguments of the project-shipped `custom.*` plugins were absent;
- DSL adaptation existed only inside a long design/TODO document;
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
| `demo/deploy_split_converter_verdict/split_config.yaml` | Shared `split_runner` config: `--role converter` publishes DSL records, `--role verdict` consumes them. |
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
| `custom.rule_based_converter:RuleBasedConverter` | `source_match` | valid Python regular-expression string | yes | none | Search pattern applied to `DataRecord.source_name`. |
| same | `field_map` | mapping: output-name string to input dot-path string | yes | none | Projects input fields into the DSL record. |
| same | `property_id` | string or null | no | null | Adds `_property_id` to produced DSL records. |
| same | `require_all` | bool | no | `false` | If true, drop a record when any mapped field is missing; otherwise drop only when none are found. |
| `custom.fleet_distance:FleetDistanceConverter` | `robot_a` | ROS namespace string | yes | none | First robot namespace; trailing slash is removed. |
| same | `robot_b` | ROS namespace string | yes | none | Second robot namespace; trailing slash is removed. |
| `custom.verdict_aggregation:LocalViolationCountConverter` | none | - | - | - | Counts currently violating local-verdict sources. |
| `custom.odom_speed_converter:OdomSpeedConverter` | none | - | - | - | Fixed demo converter for `/odom` and `twist.twist.linear.x`. |
| `custom.nav2_case1.cmd_vel_speed_converter:CmdVelSpeedConverter` | none | - | - | - | Extracts `twist.linear.x`; normally paired with `inputs: ["/cmd_vel"]`. |

### Verdict Services

| `type` | Field | Type / allowed values | Required | Default | Meaning |
|---|---|---|---:|---|---|
| `custom.threshold_verdict:ThresholdVerdict` | `property_id` | non-empty string recommended | yes | none | Identifier written into every emitted verdict. |
| same | `field` | string key present in the DSL record | yes | none | Value to compare. |
| same | `op` | one of `>`, `>=`, `<`, `<=`, `==`, `!=` | yes | none | Comparison operator; a true comparison means violation. |
| same | `threshold` | number convertible to float | yes | none | Right-hand comparison value. |
| same | `sustain_sec` | number convertible to float; `>= 0` recommended | no | `0.0` | Required continuous violation duration before firing. |
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
  `RunnerConfig` ignores it and `verdict_runner` generates its own session id.
- `actions[*].phases` silently ignores unsupported strings.
- The generation algorithm's core projection is implemented in
  `monitor/config_gen.py`: it maps a deployment JSON request (hosts / runtimes /
  links) onto the runtime YAML parsed by `MonitorConfig` / `RunnerConfig`. Plugin
  class references and constructor arguments are currently carried explicitly in
  the request. A small machine-readable manifest per `custom/` package and a
  generated JSON Schema remain future work — the manifest would let the
  generator discover those plugin class paths and constructor arguments
  automatically instead of having them written into each request.
