# Configuration Specification

> Version: 1.2 - 2026-06-15
> Implementation: `monitor/config_model.py`
> Default example: `monitor/config.yaml`

This is the normative field reference for every ROS2-Monitor-Infra runtime
YAML file. The inventory of concrete configuration files shipped by the
project, including demo and external-tool configuration, is in
[config_inventory.md](config_inventory.md).

Value descriptions distinguish between:

- **accepted by implementation**: values the current Python code can parse;
- **supported values**: values with an implemented and tested meaning;
- **recommended constraints**: narrower values that avoid invalid ROS2,
  MQTT, or filesystem configuration.

## Overview

The configuration is a YAML document consumed by these entrypoints:

| Entrypoint | Reads |
|---|---|
| `monitor/monitor_node.py` | `monitor`, `topics`, `services`, `actions`, `exporters`, `converters` |
| `monitor/verdict_runner.py` | `monitor.output_dir`, `verdict_runner.source`, `converters` |
| `monitor/split_runner.py` | `monitor.output_dir`, `verdict_runner.source` (converter/filter roles), `converters` incl. `converters[*].dsl_transport` (converter/verdict roles) and `converters[*].record_transport` (filter role) |

Plugin-like blocks share this shape:

```yaml
type: short_name_or_module.path:ClassName
...: plugin constructor kwargs
```

The exact `type` format depends on the block: exporters and sources accept
short built-in names or `module.path:ClassName`; converters and verdict
services currently require `module.path:ClassName`; transformers currently use
the built-in names listed below. Sibling keys become constructor keyword
arguments unless listed as framework-reserved fields in this document.

### Unknown and Unsupported Fields

- Unknown top-level fields and unknown fields under `monitor` are currently
  ignored by the corresponding parsed model.
- Unknown fields inside plugin-like blocks are passed as Python constructor
  keyword arguments. They are valid only if the selected plugin constructor
  accepts them; otherwise component construction fails and the component or
  converter chain is skipped.
- The tables below define the YAML-supported fields of built-in plugins.
  Constructor-only dependency-injection arguments such as `client` and
  callable arguments such as `serialize` are intentionally excluded because
  ordinary YAML cannot construct the required Python objects.
- YAML booleans should be unquoted `true` or `false`. A quoted string may be
  converted by Python's `bool()` in an unexpected way.

## Top-Level Fields

| Field | Type | Required | Default | Used by | Notes |
|---|---|---:|---|---|---|
| `monitor` | mapping | no | `{}` | both | Global runtime settings. |
| `topics` | list of `MonitoredSourceSpec` | no | `[]` | `monitor_node` | Topic collectors. |
| `services` | list of `MonitoredSourceSpec` | no | `[]` | `monitor_node` | Service event collectors. |
| `actions` | list of `MonitoredSourceSpec` | no | `[]` | `monitor_node` | Action feedback/status collectors. |
| `exporters` | list of `ExporterSpec` | no | `[]` | `monitor_node` | Global DataRecord exporters. |
| `verdict_runner` | mapping | yes for `verdict_runner`, no for `monitor_node` | `{}` | `verdict_runner` | Must contain `source` when running `verdict_runner`. |
| `converters` | list of `ConverterSpec` | no | `[]` | both | Converter/verdict chains. Required in practice when verdict evaluation is expected. |

## `monitor`

| Field | Type | Required | Default | Used by | Notes |
|---|---|---:|---|---|---|
| `output_dir` | string path | no | `"./output"` | both | Base directory for relative file outputs. May be absolute or relative to the process working directory. The process must be able to create/write it. |
| `session_id_prefix` | string | no | `""` | `monitor_node` | Prefix prepended to generated monitor session ids. Any string is accepted; use filesystem- and topic-safe characters because the value can appear in output names and evidence ids. |

`verdict_runner` reads `monitor.output_dir` to resolve relative verdict and DSL
archive paths. It generates its own verifier-side session id.

Example:

```yaml
monitor:
  output_dir: /output/verifier
  session_id_prefix: verifier1
```

## Monitored Sources

`topics`, `services`, and `actions` contain `MonitoredSourceSpec` entries.

### Common Source Fields

| Field | Type | Required | Default | Applies to | Notes |
|---|---|---:|---|---|---|
| `name` | string | yes | none | topic, service, action | ROS graph source name, such as `/odom`. Runtime skips entries with an empty name. |
| `type` | string | topic/service no, action yes | topic/service: discovered if active; action: none | topic, service, action | ROS2 message/service/action type. |
| `transformers` | list of `TransformerSpec` | no | `[]` | topic, service, action | Per-source transformer chain. |
| `exporters` | list of `ExporterSpec` | no | `[]` | topic, service, action | Per-source DataRecord exporters. If present, this source uses them instead of global `exporters`. |

### Topic Fields

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `qos` | positive int | no | `10` | QoS history depth passed to `create_subscription()`. The code converts it with `int()`; use values `>= 1`. A configured `0` is currently treated as omitted and becomes `10`. |

Example:

```yaml
topics:
  - name: /odom
    type: nav_msgs/msg/Odometry
    qos: 10
    transformers:
      - type: FieldExtractor
        fields:
          - twist.twist.linear.x
    exporters:
      - type: mqtt
        broker: 127.0.0.1
```

### Service Fields

Services use only the common source fields.

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `name` | string | yes | none | Service name. |
| `type` | string | no | discovered if active | Service type. |
| `transformers` | list of `TransformerSpec` | no | `[]` | Per-service transformer chain. |
| `exporters` | list of `ExporterSpec` | no | `[]` | Per-service DataRecord exporters. |

The monitor subscribes to `/<service_name>/_service_event`; the service server
must enable ROS2 service introspection for records to appear.

### Action Fields

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `name` | string | yes | none | Action name. |
| `type` | string | yes | none | Action type. Runtime skips entries without it. |
| `phases` | non-empty list of strings | no | `["feedback", "status"]` | Hidden action topics to subscribe to. Supported values are exactly `feedback` and `status`; unknown values are ignored. An empty list currently also selects both defaults. |
| `transformers` | list of `TransformerSpec` | no | `[]` | Per-action transformer chain. |
| `exporters` | list of `ExporterSpec` | no | `[]` | Per-action DataRecord exporters. |

Example:

```yaml
actions:
  - name: /navigate_to_pose
    type: nav2_msgs/action/NavigateToPose
    phases: [feedback, status]
```

## Transformers

Each transformer entry is a `TransformerSpec`.

### `TransformerSpec`

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `type` | string | yes | none | Built-in transformer name. Runtime skips entries with an empty or unknown type. |
| other fields | any | depends on selected transformer | none | Passed to the transformer constructor. |

### Built-In Transformer Constructor Fields

| Transformer | Field | Type | Required | Default | Notes |
|---|---|---|---:|---|---|
| `FieldExtractor` | `fields` | list of dot-path strings | yes | none | Keeps selected fields and flattens nested values into dot-notation keys. Missing paths are silently omitted. |
| `RateThrottler` | `max_rate_hz` | number | yes | none | Converted to `float`; must be greater than zero. |
| `OnChangeFilter` | `watch_fields` | list of dot-path strings | yes | none | Emits the first record, then emits only when the set of found watched values changes. Missing paths are allowed. |

## DataRecord Exporters

DataRecord exporters can be declared globally under top-level `exporters` or
per source under `topics[*].exporters`, `services[*].exporters`, or
`actions[*].exporters`.

If a source declares its own `exporters`, that source uses only those exporters
for DataRecord output. If a source does not declare exporters, it uses the
global `exporters`.

If there are no global exporters and no source-level exporters, `monitor_node`
creates a default file exporter. If there is at least one source-level exporter
and no global exporters, sources without their own exporters have no DataRecord
output, though converter chains still receive their records.

### `ExporterSpec`

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `type` | string | yes | none | Built-in exporter name or `module.path:ClassName`. Runtime skips entries with an empty or unknown type. |
| other fields | any | depends on selected exporter | exporter-specific | Passed to the exporter constructor, with framework defaults applied where documented below. |

### Built-In DataRecord Exporter Fields

| Exporter | Field | Type | Required | Default | Notes |
|---|---|---|---:|---|---|
| `file` | `output_dir` | string | no | `monitor.output_dir` | Filled by the framework if omitted. |
| `file` | `session_id` | string | no | current monitor session id | Filled by the framework if omitted. |
| `file` | `flush_every` | int | no | `1` | Values lower than one are coerced to one. |
| `file` | `filename_suffix` | string | no | global: `""`; per-source: sanitized source name | Example per-source suffix: `_cmd_vel`. |
| `mqtt` | `broker` | string | no | `"localhost"` | MQTT broker host. |
| `mqtt` | `port` | int | no | `1883` | MQTT broker port; use `1..65535`. |
| `mqtt` | `topic_prefix` | string | no | `"monitor/"` | Data records publish to `<prefix><source_type>/<source_name>`. |
| `mqtt` | `qos` | int enum | no | `1` | MQTT publish QoS: `0`, `1`, or `2`. |
| `mqtt` | `keepalive` | non-negative int | no | `60` | MQTT keepalive seconds. |
| `mqtt` | `max_queued_messages` | non-negative int | no | `1000` | Passed to paho's queue limit; `0` means unlimited in paho. |
| `mqtt` | `publish_bookends` | bool | no | `true` | If false, skips `session_start` and `session_end`. |
| `mqtt` | `client_id` | string | no | `""` | MQTT client id. |

Example:

```yaml
topics:
  - name: /odom
    type: nav_msgs/msg/Odometry
    exporters:
      - type: mqtt
        broker: 127.0.0.1
        port: 1883
```

## `converters`

Each converter entry builds one independent chain:

```text
DataRecord -> DataConverter -> VerdictService -> Verdict exporters
```

### `ConverterSpec`

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `type` | string | yes | none | `DataConverter` class as `module.path:ClassName`. Runtime skips entries with an empty or unresolvable type. |
| `inputs` | non-empty list of strings | no | omitted, converter sees all records | Exact `DataRecord.source_name` filter applied before the converter. Empty lists and non-string elements cause the chain to be skipped. |
| `output` | string | no | omitted, no DSL archive | Optional JSONL archive path for DSL-ready records. Relative paths resolve against `monitor.output_dir`; `{session_id}` is substituted. |
| `verdict` | `VerdictSpec` | yes | none | Verdict service and verdict exporters. |
| `dsl_transport` | mapping | no | omitted, in-process | Read only by `split_runner --role converter`/`verdict` (see [`split_runner`](#split_runner)). Names the MQTT topic that joins the converter and verdict halves when they run on separate hosts. Ignored by `monitor_node` and `verdict_runner`, which always run the chain in-process. |
| `record_transport` | mapping | no | omitted | Read only by `split_runner --role filter` (see [`split_runner`](#split_runner)). Names the file or MQTT carrier a `data_filter` converter republishes `DataRecord`s through, so it can feed a downstream converter on another host. Ignored by every other entrypoint. |
| other fields | any | depends on selected converter | none | Passed to the converter constructor. |

Example:

```yaml
converters:
  - type: custom.odom_speed_converter:OdomSpeedConverter
    verdict:
      type: custom.odom_speed_verdict:OdomSpeedVerdict
      exporters:
        - type: stdout
        - type: file
          path: verdicts_{session_id}.jsonl
```

### `VerdictSpec`

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `type` | string | yes | none | `VerdictService` class as `module.path:ClassName`. Runtime skips chains with an empty or unresolvable type. |
| `exporters` | list of `ExporterSpec` | no | `[]`, which means stdout fallback | Verdict output exporters. |
| other fields | any | depends on selected verdict service | none | Passed to the verdict service constructor. |

## Verdict Exporters

Verdict exporters are declared under `converters[*].verdict.exporters`.

If `exporters` is omitted or empty, verdicts are printed to stdout by the
default `VerdictExporter`.

### Built-In Verdict Exporter Fields

| Exporter | Field | Type | Required | Default | Notes |
|---|---|---|---:|---|---|
| `file` | `path` | string | yes | none | JSONL output path. Relative paths resolve against `monitor.output_dir`. |
| `file` | `flush_every` | int | no | `1` | Values lower than one are coerced to one. |
| `stdout` | none | - | - | - | No constructor fields. |
| `mqtt` | `topic` | string | yes | none | MQTT topic for verdict JSON strings. |
| `mqtt` | `broker` | string | no | `"localhost"` | MQTT broker host. |
| `mqtt` | `port` | int | no | `1883` | MQTT broker port; use `1..65535`. |
| `mqtt` | `qos` | int enum | no | `1` | MQTT publish QoS: `0`, `1`, or `2`. |
| `mqtt` | `keepalive` | non-negative int | no | `60` | MQTT keepalive seconds. |
| `mqtt` | `max_queued_messages` | non-negative int | no | `1000` | Passed to paho's queue limit; `0` means unlimited in paho. |
| `mqtt` | `client_id` | string | no | `""` | MQTT client id. |

All string kwargs under `verdict.exporters` support `{session_id}`
substitution. This session id is:

| Runtime | `{session_id}` value |
|---|---|
| `monitor_node` integrated mode | Monitor session id. |
| `verdict_runner` split mode | Verifier runner session id. |

## `verdict_runner`

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `source` | `SourceSpec` | yes when running `verdict_runner` | none | Inbound DataRecord transport. |

Example:

```yaml
verdict_runner:
  source:
    type: mqtt
    broker: 127.0.0.1
    topic_filter: monitor/#
```

### `SourceSpec`

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `type` | string | yes | none | Built-in source name or `module.path:ClassName`. `verdict_runner` exits if missing or unresolvable. |
| other fields | any | depends on selected source | source-specific | Passed to the source constructor. |

### Built-In Source Fields

| Source | Field | Type | Required | Default | Notes |
|---|---|---|---:|---|---|
| `file` | `path` | string | yes | none | JSONL file containing serialized DataRecords. |
| `file` | `interval_sec` | non-negative number | no | `0.0` | Delay between replayed records. Negative values are coerced to `0.0`. |
| `file` | `loop` | bool | no | `false` | Replay again after EOF. |
| `mqtt` | `broker` | string | no | `"localhost"` | MQTT broker host. |
| `mqtt` | `port` | int | no | `1883` | MQTT broker port; use `1..65535`. |
| `mqtt` | `topic_filter` | string | no | `"monitor/#"` | MQTT subscription filter. |
| `mqtt` | `qos` | int enum | no | `1` | MQTT subscribe QoS: `0`, `1`, or `2`. |
| `mqtt` | `keepalive` | non-negative int | no | `60` | MQTT keepalive seconds. |
| `mqtt` | `client_id` | string | no | `""` | MQTT client id. |

## `split_runner`

`monitor/split_runner.py` runs the converter half and the verdict half of one
or more chains as **separate processes**, joined by an MQTT DSL-record
transport. `verdict_runner` always runs both halves in-process; `split_runner`
is the entrypoint that lets them live on different hosts.

It reuses the same YAML; the converter half and the verdict half each read only
what they need, so the same file can be deployed to both hosts. Select the half
with `--role`:

| `--role` | Reads | Behavior |
|---|---|---|
| `converter` | `verdict_runner.source`, `converters[*].{type, inputs, dsl_transport, kwargs}` | Consumes DataRecords from `verdict_runner.source`, runs each converter, and publishes its DSL records to that converter's `dsl_transport` topic. |
| `verdict` | `monitor.output_dir`, `converters[*].{dsl_transport, output, verdict}` | Subscribes to each converter's `dsl_transport` topic and runs the paired verdict stage (`VerdictService` + verdict exporters). |
| `filter` | `verdict_runner.source`, `converters[*].{type, inputs, record_transport, kwargs}` | Consumes DataRecords from `verdict_runner.source`, runs each converter, and **republishes DataRecords** through that converter's `record_transport`. This is the converter→converter seam: a `data_filter` converter (one that returns a `DataRecord`, not a DSL dict) feeds a downstream converter on another host, which reads the same carrier as an ordinary source. |

A converter without a `dsl_transport` block is skipped by `--role converter` /
`--role verdict`; one without a `record_transport` block is skipped by
`--role filter`. Use `verdict_runner` for in-process chains.

### `dsl_transport` fields

The transported payload is the converter's DSL-ready record; see
[dsl_record_spec.md](dsl_record_spec.md) for its schema.

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `topic` | string | yes | none | MQTT topic carrying this chain's DSL records. Use a distinct topic per converter so each verdict stage receives only its own records. |
| `broker` | string | no | `"localhost"` | MQTT broker host. |
| `port` | int | no | `1883` | MQTT broker port; use `1..65535`. |
| `qos` | int enum | no | `1` | MQTT publish/subscribe QoS: `0`, `1`, or `2`. |
| `keepalive` | non-negative int | no | `60` | MQTT keepalive seconds. |

### `record_transport` fields

Read only by `--role filter`. The transported payload is a `DataRecord` (the
same wire form as a monitor feed), so a `data_filter` converter can chain into a
downstream converter. The `kind` selects the carrier; the downstream host reads
the same namespace with an ordinary `mqtt` or `file` source.

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `kind` | string | no | `"mqtt"` | Carrier: `mqtt` or `file`. |
| `topic_prefix` | string | `kind=mqtt`: yes | none | MQTT topic prefix the filtered DataRecords are republished under (e.g. `filtered/`). Use a namespace distinct from the upstream feed. Records publish to `<topic_prefix><source_type>/<source_name>`; the downstream `mqtt` source uses `topic_filter: <topic_prefix>#`. |
| `output_dir` | string | `kind=file`: yes | none | Directory the filtered DataRecords are appended to as JSONL. The downstream `file` source reads `<output_dir>/<session_id>.jsonl`. |
| `session_id` | string | `kind=file`: yes | none | Stem of the shared JSONL file. |
| `broker` / `port` / `qos` / `keepalive` | — | no | mqtt defaults | MQTT connection fields (`kind=mqtt` only). |

`monitor/config_gen.py` fills these from a `records` link between two converters,
choosing `mqtt` or `file` from the link's `transport.kind` and deriving a shared
namespace from the link id so the filter output and the downstream source always
agree. DSL links remain MQTT-only (there is no file-based DSL transport); the
generator rejects `kind: file` on a `dsl` link with an explicit error.

Example (one file, deployed to both the converter and verdict hosts):

```yaml
monitor:
  output_dir: /output/verifier

verdict_runner:
  source:                       # read by --role converter
    type: mqtt
    broker: 127.0.0.1
    topic_filter: monitor/#

converters:
  - type: custom.odom_speed_converter:OdomSpeedConverter
    dsl_transport:              # the seam between the two hosts
      broker: 127.0.0.1
      topic: dsl/odom_speed
    verdict:                    # run by --role verdict
      type: custom.odom_speed_verdict:OdomSpeedVerdict
      exporters:
        - type: stdout
        - type: file
          path: verdicts_{session_id}.jsonl
```

Run (`demo/deploy_split_converter_verdict` is the worked example):

```bash
python monitor/split_runner.py --role verdict   -c <config>
python monitor/split_runner.py --role converter -c <config>
```

## Parsed Model Reference

| Dataclass | Source YAML | Defaults |
|---|---|---|
| `MonitorConfig` | Full YAML for `monitor_node` | See top-level and `monitor` tables. |
| `RunnerConfig` | Full YAML for `verdict_runner` and `split_runner` | `output_dir="./output"`, `converters=[]`, `source=None`. |
| `MonitoredSourceSpec` | Entries under `topics`, `services`, `actions` | `transformers=[]`, `exporters=[]`, `qos=None`, `phases=None`. |
| `TransformerSpec` | Entries under source `transformers` | `kwargs={}`, `raw={}`. |
| `ExporterSpec` | DataRecord exporters and verdict exporters | `kwargs={}`, `raw={}`. |
| `ConverterSpec` | Entries under `converters` | `inputs=None`, `output=None`, `dsl_transport=None`, `record_transport=None`. |
| `VerdictSpec` | Nested `verdict` blocks | `exporters=[]`. |
| `SourceSpec` | `verdict_runner.source` | `kwargs={}`, `raw={}`. |

Each plugin spec retains:

| Field | Type | Required | Default | Meaning |
|---|---|---:|---|---|
| `type` | string | yes | none | Built-in short name or import path. |
| `kwargs` | mapping | no | `{}` | Constructor kwargs after reserved framework keys are removed. |
| `raw` | mapping | no | `{}` | Original YAML mapping for logging and diagnostics. |

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
  - type: custom.odom_speed_converter:OdomSpeedConverter
    verdict:
      type: custom.odom_speed_verdict:OdomSpeedVerdict
      exporters:
        - type: stdout
```

### Split Monitor / Verdict Runner

Robot-side monitor:

```yaml
monitor:
  output_dir: ./output/robot

topics:
  - name: /odom
    type: nav_msgs/msg/Odometry
    exporters:
      - type: mqtt
        broker: broker.local
        topic_prefix: monitor/robot1/
```

Verifier-side runner:

```yaml
monitor:
  output_dir: ./output/verifier

verdict_runner:
  source:
    type: mqtt
    broker: broker.local
    topic_filter: monitor/robot1/#

converters:
  - type: custom.odom_speed_converter:OdomSpeedConverter
    verdict:
      type: custom.odom_speed_verdict:OdomSpeedVerdict
      exporters:
        - type: file
          path: verdicts_{session_id}.jsonl
```
