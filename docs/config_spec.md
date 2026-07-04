# Configuration Specification

> Version: 2.0 - 2026-07-04
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

| Entrypoint | Reads | Needs ROS2 |
|---|---|---|
| `monitor/monitor_node.py` | `monitor`, `topics`, `services`, `actions`, `exporters`, `converters`, `verdict_services`, `outputs`, `links` | yes |
| `monitor/node_runner.py` | `monitor.output_dir`, `inputs`, `converters`, `verdict_services`, `outputs`, `links` | no |

`monitor_node` collects records from the ROS graph; `node_runner` receives
them (or DSL records) through `inputs:` endpoints. Both run the same
evaluation graph, so what a host does is decided entirely by its YAML — a
single `node_runner` process can be a filter relay, a converter half, a
verdict half, or any mix.

Plugin-like blocks share this shape:

```yaml
type: short_name_or_module.path:ClassName
...: plugin constructor kwargs
```

The exact `type` format depends on the block: exporters, sources, and
transport endpoints accept short built-in names or `module.path:ClassName`;
converters and verdict services require `module.path:ClassName`; transformers
use the built-in names listed below. Sibling keys become constructor keyword
arguments unless listed as framework-reserved fields in this document.
Converter and verdict blocks prefer an explicit `params:` mapping for
constructor kwargs.

### Unknown and Unsupported Fields

- Unknown top-level fields and unknown fields under `monitor` are currently
  ignored by the corresponding parsed model.
- Unknown fields inside plugin-like blocks are passed as Python constructor
  keyword arguments. They are valid only if the selected plugin constructor
  accepts them; otherwise component construction fails and the component is
  skipped.
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
| `inputs` | list of `EndpointSpec` | yes for `node_runner` | `[]` | `node_runner` | Inbound transport endpoints. |
| `converters` | list of `ConverterSpec` | no | `[]` | both | Converter nodes. |
| `verdict_services` | list of `VerdictSpec` | no | `[]` | both | Verdict-service nodes. |
| `outputs` | list of `EndpointSpec` | no | `[]` | both | Outbound transport endpoints. |
| `links` | list of link mappings | no | `[]` | both | Graph edges (see [`links`](#links)). |

## `monitor`

| Field | Type | Required | Default | Used by | Notes |
|---|---|---:|---|---|---|
| `output_dir` | string path | no | `"./output"` | both | Base directory for relative file outputs. May be absolute or relative to the process working directory. The process must be able to create/write it. |
| `session_id_prefix` | string | no | `""` | `monitor_node` | Prefix prepended to generated monitor session ids. Any string is accepted; use filesystem- and topic-safe characters because the value can appear in output names and evidence ids. |

`node_runner` reads `monitor.output_dir` to resolve relative verdict and DSL
paths. It generates its own runner-side session id.

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

The monitor subscribes to `/<service_name>/_service_event`; the service server
must enable ROS2 service introspection for records to appear.

### Action Fields

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `name` | string | yes | none | Action name. |
| `type` | string | yes | none | Action type. Runtime skips entries without it. |
| `phases` | non-empty list of strings | no | `["feedback", "status"]` | Hidden action topics to subscribe to. Supported values are exactly `feedback` and `status`; unknown values are ignored. An empty list currently also selects both defaults. |

Example:

```yaml
actions:
  - name: /navigate_to_pose
    type: nav2_msgs/action/NavigateToPose
    phases: [feedback, status]
```

## Transformers

Each transformer entry is a `TransformerSpec`.

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
output, though the evaluation graph still receives their records.

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

## Evaluation Graph

The runtime shape separates component configuration from routing. Nodes are
declared under `inputs`, `converters`, `verdict_services`, and `outputs`;
`links` wires them:

```text
source:<DataRecord.source_name> -> converter:<id>     record selection
input:<id>                      -> verdict:<id>       inbound dsl feed
input:<id>                      -> output:<id>        dsl relay / archive
converter:<id>                  -> converter:<id>     in-process chaining
converter:<id>                  -> verdict:<id>       in-process evaluation
converter:<id>                  -> output:<id>        outbound transport
```

A converter can receive multiple sources and can fan out to multiple verdict
services, downstream converters, and outputs. A stateful verdict service is
instantiated once even if multiple converters (or inputs) feed it.
`converter -> converter` links must not form a cycle; a cycle fails the whole
graph with an error.

A converter that only appears as the target of `converter -> converter` links
(and declares no `source:` link or `inputs:` filter) is *chained-only*: it
receives records exclusively from its upstream converter, not from the shared
record stream.

### `ConverterSpec`

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `id` | string | yes for graph wiring | falls back to `type` | Stable node id referenced by links as `converter:<id>`. |
| `type` | string | yes | none | `DataConverter` class as `module.path:ClassName`. Runtime skips entries with an empty or unresolvable type. |
| `params` | mapping | no | `{}` | Constructor kwargs for the converter. |
| `inputs` | non-empty list of strings | no | derived from `source:*` links; omitted = all records | Exact `DataRecord.source_name` filter. `source:*` links take precedence when present. |
| other fields | any | depends on selected converter | none | Also accepted as constructor kwargs; `params` is preferred. |

A converter class may implement the optional lifecycle
(`start(emit)` / `stop()`) to emit records on its own schedule in addition to
the reactive `convert()` path — see
[dsl_adaptation_guide.md](dsl_adaptation_guide.md).

### `VerdictSpec` / `verdict_services`

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `id` | string | yes for graph wiring | falls back to `type` | Stable node id referenced by links as `verdict:<id>`. |
| `type` | string | yes | none | `VerdictService` class as `module.path:ClassName`. Runtime skips entries with an empty or unresolvable type. |
| `params` | mapping | no | `{}` | Constructor kwargs for the verdict service. |
| `exporters` | list of `ExporterSpec` | no | `[]`, which means stdout fallback | Verdict output exporters. |
| other fields | any | depends on selected verdict service | none | Also accepted as constructor kwargs; `params` is preferred. |

### `links`

| Field | Type | Required | Notes |
|---|---|---:|---|
| `id` | string | no | Human/debug identifier. |
| `from` | string | yes | `source:<source_name>`, `input:<id>`, or `converter:<id>`. |
| `to` | string | yes | `converter:<id>`, `verdict:<id>`, or `output:<id>`. |

Example:

```yaml
converters:
  - id: demo1-velocity-converter
    type: custom.demo1_velocity_converter:Demo1VelocityConverter
    params:
      speed_path: linear.x

verdict_services:
  - id: demo1-speeding-check
    type: custom.demo1_speeding_check:Demo1SpeedingCheck
    params:
      check: speed
      op: ">"
      value: 0.5
    exporters:
      - type: stdout
      - type: file
        path: verdicts_{session_id}.jsonl

links:
  - from: source:/cmd_vel
    to: converter:demo1-velocity-converter
  - from: converter:demo1-velocity-converter
    to: verdict:demo1-speeding-check
```

## Transport Endpoints (`inputs` / `outputs`)

An `EndpointSpec` names one inbound or outbound transport. The `payload`
selects the wire format, the `type` the carrier.

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `id` | string | recommended | `endpoint_<n>` | Referenced by links as `input:<id>` / `output:<id>`. |
| `payload` | string | no | `"records"` | `records` (DataRecords) or `dsl` (converter output). |
| `type` | string | yes | none (outputs default: dsl→`mqtt`, records→`file`) | Built-in carrier name or `module.path:ClassName`. |
| other fields | any | carrier-specific | see below | Passed to the carrier constructor. `{session_id}` is substituted in string kwargs of outputs. |

Routing semantics:

- **records inputs** all fan into the shared record stream; converters select
  from it by source name. They are not link targets.
- **dsl inputs** must be routed explicitly with `input:<id> -> verdict:<id>`
  (or `-> output:<id>` for a relay/archive).
- **outputs** receive whatever the linked converter (or input) emits: use
  `payload: dsl` for converters returning DSL dicts, `payload: records` for
  filter converters returning DataRecords.

### Built-In Carrier Fields

Records endpoints use the DataRecord transports:

| Direction | Carrier | Field | Type | Required | Default | Notes |
|---|---|---|---|---:|---|---|
| input | `mqtt` | `broker` / `port` / `topic_filter` / `qos` / `keepalive` / `client_id` | — | no | `localhost` / `1883` / `monitor/#` / `1` / `60` / `""` | MQTT subscription. |
| input | `file` | `path` | string | yes | none | JSONL file of serialized DataRecords. |
| input | `file` | `interval_sec` | non-negative number | no | `0.0` | Delay between replayed records. |
| input | `file` | `loop` | bool | no | `false` | Replay again after EOF. |
| input | `file` | `follow` | bool | no | `false` | Keep reading appended lines (live cross-host file link). |
| output | `mqtt` | same as DataRecord `mqtt` exporter | — | no | — | Records publish to `<topic_prefix><source_type>/<source_name>`. |
| output | `file` | same as DataRecord `file` exporter | — | no | framework defaults | Appends `<output_dir>/<session_id><suffix>.jsonl`. |

DSL endpoints use the DSL-record transports (payload schema in
[dsl_record_spec.md](dsl_record_spec.md)):

| Direction | Carrier | Field | Type | Required | Default | Notes |
|---|---|---|---|---:|---|---|
| both | `mqtt` | `topic` | string | yes | none | Single MQTT topic carrying the DSL records. Use a distinct topic per link. |
| both | `mqtt` | `broker` / `port` / `qos` / `keepalive` / `client_id` | — | no | mqtt defaults | Connection settings. |
| output | `file` | `path` | string | yes | none | JSONL path; relative paths resolve against `monitor.output_dir`. |
| output | `file` | `flush_every` | int | no | `1` | Values lower than one are coerced to one. |
| input | `file` | `path` | string | yes | none | JSONL path to read. |
| input | `file` | `interval_sec` / `loop` / `follow` | — | no | `0.0` / `false` / `false` | Replay pacing / tail semantics, as for records. |

Example (converter host and verdict host, joined by one MQTT topic):

```yaml
# converter host
inputs:
  - id: robot_feed
    type: mqtt
    topic_filter: monitor/#
converters:
  - id: odom_speed
    type: custom.odom_speed_converter:OdomSpeedConverter
outputs:
  - id: dsl_out
    payload: dsl
    type: mqtt
    topic: dsl/odom_speed
links:
  - {from: "converter:odom_speed", to: "output:dsl_out"}
```

```yaml
# verdict host
inputs:
  - id: dsl_in
    payload: dsl
    type: mqtt
    topic: dsl/odom_speed
verdict_services:
  - id: odom_speed_check
    type: custom.odom_speed_verdict:OdomSpeedVerdict
    exporters:
      - type: stdout
links:
  - {from: "input:dsl_in", to: "verdict:odom_speed_check"}
```

Run both with:

```bash
python monitor/node_runner.py -c <config>
```

## Verdict Exporters

Verdict exporters are declared under `verdict_services[*].exporters`.

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

All string kwargs under verdict exporters support `{session_id}`
substitution. This session id is:

| Runtime | `{session_id}` value |
|---|---|
| `monitor_node` | Monitor session id. |
| `node_runner` | Runner session id. |

## Parsed Model Reference

| Dataclass | Source YAML | Defaults |
|---|---|---|
| `MonitorConfig` | Full YAML for `monitor_node` | See top-level and `monitor` tables. |
| `RunnerConfig` | Full YAML for `node_runner` | `output_dir="./output"`, all lists empty. |
| `MonitoredSourceSpec` | Entries under `topics`, `services`, `actions` | `transformers=[]`, `exporters=[]`, `qos=None`, `phases=None`. |
| `TransformerSpec` | Entries under source `transformers` | `kwargs={}`, `raw={}`. |
| `ExporterSpec` | DataRecord exporters and verdict exporters | `kwargs={}`, `raw={}`. |
| `EndpointSpec` | Entries under `inputs` and `outputs` | `payload="records"`, `kwargs={}`. |
| `ConverterSpec` | Entries under `converters` | `inputs=None`. |
| `VerdictSpec` | Entries under `verdict_services` | `exporters=[]`. |
| `RuntimeLinkSpec` | Entries under `links` | `id=None`. |

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
  - id: odom_speed
    type: custom.odom_speed_converter:OdomSpeedConverter

verdict_services:
  - id: odom_speed_check
    type: custom.odom_speed_verdict:OdomSpeedVerdict
    exporters:
      - type: stdout

links:
  - {from: "source:/odom", to: "converter:odom_speed"}
  - {from: "converter:odom_speed", to: "verdict:odom_speed_check"}
```

### Split Monitor / Node Runner

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

inputs:
  - id: robot_feed
    type: mqtt
    broker: broker.local
    topic_filter: monitor/robot1/#

converters:
  - id: odom_speed
    type: custom.odom_speed_converter:OdomSpeedConverter

verdict_services:
  - id: odom_speed_check
    type: custom.odom_speed_verdict:OdomSpeedVerdict
    exporters:
      - type: file
        path: verdicts_{session_id}.jsonl

links:
  - {from: "converter:odom_speed", to: "verdict:odom_speed_check"}
```
