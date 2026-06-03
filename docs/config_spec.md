# Configuration Specification

> Version: 1.0 — 2026-06-03
> Implementation: `monitor/config_model.py`
> Default example: `monitor/config.yaml`

## Overview

The monitor configuration is a YAML document consumed by two entrypoints:

| Entrypoint | Reads |
|---|---|
| `monitor/monitor_node.py` | `monitor`, `topics`, `services`, `actions`, `exporters`, `converters` |
| `monitor/verdict_runner.py` | `monitor.output_dir`, `verdict_runner.source`, `converters` |

The same YAML can therefore describe both deployment styles:

1. **Integrated monitor + verdict evaluation** on the robot: `monitor_node`
   captures ROS2 data and also runs converter/verdict chains locally.
2. **Split monitor/verifier deployment**: `monitor_node` exports
   `DataRecord` messages through a transport such as MQTT, while
   `verdict_runner` consumes them through `verdict_runner.source`.

All plugin-like blocks use the same shape:

```yaml
type: short_name_or_module.path:ClassName
...: plugin constructor kwargs
```

`type` selects a built-in or user-defined class. All sibling keys become
constructor keyword arguments unless this document explicitly reserves them.

---

## Top-Level Shape

```yaml
monitor: {...}
topics: [...]
services: [...]
actions: [...]
exporters: [...]
verdict_runner:
  source: {...}
converters: [...]
```

All top-level lists are optional. Missing lists parse as empty lists.

---

## `monitor`

Global monitor settings.

| Key | Type | Default | Consumed by | Purpose |
|---|---|---|---|---|
| `output_dir` | `string` | `"./output"` | `monitor_node`, `verdict_runner` | Base directory for relative file outputs. |
| `session_id_prefix` | `string` | `""` | `monitor_node` | Optional prefix prepended to generated monitor session ids. |

Example:

```yaml
monitor:
  output_dir: ./output/nav2
  session_id_prefix: robot1
```

`verdict_runner` reads `monitor.output_dir` only to resolve relative verdict
exporter paths. It generates its own verifier-side session id.

---

## Monitored Sources

`topics`, `services`, and `actions` are lists of `MonitoredSourceSpec`.

### Common Source Keys

| Key | Type | Required | Applies to | Purpose |
|---|---|---|---|---|
| `name` | `string` | yes | topic, service, action | ROS graph source name, such as `/odom` or `/navigate_to_pose`. |
| `type` | `string` | topic/service optional, action required | topic, service, action | ROS2 message/service/action type. Topics and services can be discovered at startup if active. |
| `transformers` | `list[TransformerSpec]` | no | topic, service, action | Per-source transformer chain. |
| `exporters` | `list[ExporterSpec]` | no | topic, service, action | Per-source DataRecord exporters. Replaces global exporters for that source. |

### Topic Keys

| Key | Type | Default | Purpose |
|---|---|---|---|
| `qos` | `int` | `10` | QoS depth passed to `create_subscription()`. |

Example:

```yaml
topics:
  - name: /odom
    type: nav_msgs/msg/Odometry
    qos: 10
    transformers:
      - type: FieldExtractor
        fields:
          - pose.pose.position.x
          - twist.twist.linear.x
```

### Service Keys

Services use the common keys only.

The monitor subscribes to `/<service_name>/_service_event`; the service
server must enable ROS2 service introspection for records to appear.

Example:

```yaml
services:
  - name: /set_bool
    type: std_srvs/srv/SetBool
```

### Action Keys

| Key | Type | Default | Purpose |
|---|---|---|---|
| `phases` | `list[string]` | `["feedback", "status"]` | Hidden action topics to subscribe to. Currently supported: `feedback`, `status`. |

`type` is required for actions because action type discovery is not currently
implemented by `MonitorNode`.

Example:

```yaml
actions:
  - name: /navigate_to_pose
    type: nav2_msgs/action/NavigateToPose
    phases: [feedback, status]
```

---

## Transformers

Transformer specs are plugin specs. Built-ins:

| Type | Constructor kwargs | Effect |
|---|---|---|
| `FieldExtractor` | `fields: list[string]` | Keeps selected fields and flattens them into dot-notation keys. |
| `RateThrottler` | `max_rate_hz: float` | Drops records faster than the configured rate. |
| `OnChangeFilter` | `watch_fields: list[string]` | Emits only when watched field values change. |

Example:

```yaml
transformers:
  - type: FieldExtractor
    fields:
      - twist.linear.x
      - twist.angular.z
  - type: RateThrottler
    max_rate_hz: 5.0
```

Transformer specs are parsed as `TransformerSpec(type, kwargs, raw)`.
All keys except `type` are passed to the transformer constructor.

---

## DataRecord Exporters

Top-level `exporters` configure the global DataRecord export stream.
Per-source `exporters` override the global stream for that source.

Built-ins:

| Type | Constructor kwargs | Output |
|---|---|---|
| `file` | `output_dir`, `session_id`, `flush_every`, `filename_suffix` | JSONL file. `output_dir` and `session_id` are filled by the framework if omitted. |
| `mqtt` | `broker`, `port`, `topic_prefix`, `qos`, `keepalive`, `max_queued_messages`, `publish_bookends`, `client_id` | Publishes DataRecords as JSON strings. |

User-defined DataRecord exporters are supported with
`type: module.path:ClassName`. The class must subclass `Exporter`.

Example:

```yaml
exporters:
  - type: file
  - type: mqtt
    broker: localhost
    port: 1883
    topic_prefix: monitor/
    qos: 1
```

Per-source example:

```yaml
topics:
  - name: /cmd_vel
    type: geometry_msgs/msg/Twist
    exporters:
      - type: file
```

For per-source file exporters, `filename_suffix` defaults to a sanitized source
name such as `_cmd_vel`.

---

## `converters`

Each converter entry builds one independent DSL evaluation chain:

```text
DataRecord -> DataConverter -> VerdictService -> Verdict exporters
```

### Converter Keys

| Key | Type | Required | Purpose |
|---|---|---|---|
| `type` | `string` | yes | `DataConverter` class, always `module.path:ClassName`. |
| `inputs` | `list[string]` | no | Source-name filter applied by the framework before the converter sees records. |
| `output` | `string` | no | Optional JSONL archive path for DSL-ready records. Relative paths resolve against `monitor.output_dir`. |
| `verdict` | `VerdictSpec` | yes | Verdict service and its output exporters. |

All other keys become converter constructor kwargs.

Example:

```yaml
converters:
  - type: custom.rule_based_converter:RuleBasedConverter
    inputs: ["/odom"]
    source_match: "^/odom$"
    field_map:
      velocity: twist.twist.linear.x
    property_id: odom_speed_limit
    verdict:
      type: custom.threshold_verdict:ThresholdVerdict
      property_id: odom_speed_limit
      field: velocity
      op: ">"
      threshold: 0.5
      exporters:
        - type: file
          path: verdicts_{session_id}.jsonl
```

`inputs` is preferred over duplicating source-name checks inside custom
converters. If omitted, the converter sees all data records.

### `verdict`

| Key | Type | Required | Purpose |
|---|---|---|---|
| `type` | `string` | yes | `VerdictService` class, always `module.path:ClassName`. |
| `exporters` | `list[ExporterSpec]` | no | Verdict output exporters. Empty or missing means stdout fallback. |

All other keys become verdict service constructor kwargs.

---

## Verdict Exporters

Built-ins:

| Type | Constructor kwargs | Output |
|---|---|---|
| `file` | `path`, `flush_every` | Appends verdict JSONL to `path`. Relative `path` resolves against `monitor.output_dir`. |
| `stdout` | none | Prints verdicts to stdout. |
| `mqtt` | `topic`, `broker`, `port`, `qos`, `keepalive`, `max_queued_messages`, `client_id` | Publishes each verdict JSON string to one topic. |

User-defined verdict exporters are supported with
`type: module.path:ClassName`. The class must subclass `Exporter`.

All string kwargs under `verdict.exporters` support `{session_id}`
substitution. This session id is:

| Runtime | `{session_id}` value |
|---|---|
| `monitor_node` integrated mode | Monitor session id. |
| `verdict_runner` split mode | Verifier runner session id. |

---

## `verdict_runner`

Configuration for `monitor/verdict_runner.py`.

| Key | Type | Required | Purpose |
|---|---|---|---|
| `source` | `SourceSpec` | yes for `verdict_runner` | Inbound DataRecord transport. |

Example:

```yaml
verdict_runner:
  source:
    type: mqtt
    broker: localhost
    port: 1883
    topic_filter: monitor/#
    qos: 1
```

Built-in sources:

| Type | Constructor kwargs | Input |
|---|---|---|
| `mqtt` | `broker`, `port`, `topic_filter`, `qos`, `keepalive`, `client_id` | MQTT payloads containing serialized DataRecords. |

User-defined sources are supported with `type: module.path:ClassName`. The
class must subclass `Source`.

---

## Parsed Model Reference

The YAML is parsed into these dataclasses:

| Dataclass | Source YAML |
|---|---|
| `MonitorConfig` | Full YAML for `monitor_node`. |
| `RunnerConfig` | Full YAML for `verdict_runner`, reduced to runner fields. |
| `MonitoredSourceSpec` | Entries under `topics`, `services`, `actions`. |
| `TransformerSpec` | Entries under source `transformers`. |
| `ExporterSpec` | DataRecord exporters and verdict exporters. |
| `ConverterSpec` | Entries under `converters`. |
| `VerdictSpec` | Nested `verdict` blocks. |
| `SourceSpec` | `verdict_runner.source`. |

Each plugin spec retains:

| Field | Meaning |
|---|---|
| `type` | Built-in short name or import path. |
| `kwargs` | Constructor kwargs after reserved framework keys are removed. |
| `raw` | Original YAML mapping for logging and diagnostics. |

---

## Minimal Examples

### Integrated Monitor

```yaml
monitor:
  output_dir: ./output

topics:
  - name: /odom
    type: nav_msgs/msg/Odometry

exporters:
  - type: file

converters:
  - type: custom.rule_based_converter:RuleBasedConverter
    source_match: "^/odom$"
    field_map:
      velocity: twist.twist.linear.x
    verdict:
      type: custom.threshold_verdict:ThresholdVerdict
      property_id: odom_speed_limit
      field: velocity
      op: ">"
      threshold: 0.5
      exporters:
        - type: stdout
```

### Split Monitor / Verdict Runner

Robot-side monitor:

```yaml
monitor:
  output_dir: ./output

topics:
  - name: /odom
    type: nav_msgs/msg/Odometry

exporters:
  - type: mqtt
    broker: broker.local
    topic_prefix: monitor/robot1/
```

Verifier-side runner reads the same YAML section shape:

```yaml
verdict_runner:
  source:
    type: mqtt
    broker: broker.local
    topic_filter: monitor/robot1/#

converters:
  - type: custom.rule_based_converter:RuleBasedConverter
    inputs: ["/odom"]
    source_match: "^/odom$"
    field_map:
      velocity: twist.twist.linear.x
    verdict:
      type: custom.threshold_verdict:ThresholdVerdict
      property_id: odom_speed_limit
      field: velocity
      op: ">"
      threshold: 0.5
      exporters:
        - type: file
          path: verdicts_{session_id}.jsonl
```
