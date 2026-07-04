# DSL Record Specification

> Version: 1.0 — 2026-06-29
> Producer: `DataConverter.convert()` (`monitor/converter.py`)
> Consumers: `VerdictService.evaluate()` (`monitor/verdict.py`) and the dsl
> transport endpoints (`monitor/dsl_transport.py`)

## Overview

A **DSL record** is the data unit exchanged between the two DSL-layer stages:

```text
DataRecord --DataConverter.convert()--> DSL record --VerdictService.evaluate()--> Verdict
```

A `DataConverter` projects a `DataRecord` (see [datarecord_spec.md](datarecord_spec.md))
into a DSL record shaped for its paired `VerdictService`. The framework treats
the DSL record as opaque (`convert` is typed `-> Any | None`), but **every
shipped converter, and the contract below, use a flat JSON-serializable
`dict`** — and the split transport requires it (see
[Serialization](#serialization-and-transport)).

Returning `None` from `convert()` drops the record (wrong source, missing
field, nothing to evaluate); see `ConverterExporter` in `monitor/converter.py`.

This record is normally an in-process object handed straight to the verdict
stage. When the converter and verdict run on different hosts (a dsl
`outputs:` endpoint on one side, a dsl `inputs:` endpoint on the other; see
[config_spec.md](config_spec.md#transport-endpoints-inputs--outputs)), it is
serialized to JSON, sent over MQTT or a shared JSONL file, and parsed back
into a dict on the verdict host — so the schema here is also the **wire
contract** for that split.

---

## Structure

A DSL record has two groups of keys:

1. **Domain payload keys** — chosen by the converter, read by the verdict
   service. Arbitrary names (e.g. `speed`, `velocity`, `distance`).
2. **Reserved framework keys** — underscore-prefixed, by convention. They carry
   correlation/identity metadata. Some are read by the framework
   (`_attach_correlation` in `monitor/verdict.py`), others are a cross-plugin
   convention the shipped converters and verdict services agree on.

```json
{
  "velocity": 0.4,                              // domain payload
  "_source_name": "/odom",                      // reserved (convention)
  "_session_id": "20260415_211500_a1b2c3d4",    // reserved (read by framework)
  "_record_id": "…:topic:/odom:-:7",            // reserved (read by framework)
  "_timestamp": 1776283880.63,                  // reserved (read by verdict services)
  "_property_id": "odom_speed_limit"            // reserved (convention)
}
```

---

## Reserved Field Reference

### `_session_id`

| | |
|---|---|
| **Type** | `string` |
| **Source** | Converter copies `DataRecord.session_id`. |
| **Read by framework** | Yes. `_attach_correlation` copies it into the emitted `Verdict.monitor_session_id` (when that field is otherwise empty). |
| **Purpose** | Links a verdict back to the monitoring session that produced the input. |

### `_record_id`

| | |
|---|---|
| **Type** | `string` |
| **Source** | Converter copies `DataRecord.record_id` (format `<session_id>:<source_type>:<source_name>:<phase-or->:<seq>`). |
| **Read by framework** | Yes, as a fallback. If `_input_record_ids` is absent, `_attach_correlation` sets `Verdict.input_record_ids = [_record_id]`. |
| **Purpose** | Traces a verdict to the exact input record. |

### `_input_record_ids`

| | |
|---|---|
| **Type** | `array[string]` |
| **Source** | Converters that fold **multiple** inputs into one DSL record (e.g. `custom.fleet_distance`) list all contributing `record_id`s here. |
| **Read by framework** | Yes, preferred over `_record_id`. `_attach_correlation` copies it into `Verdict.input_record_ids`. |
| **Purpose** | Multi-input provenance (e.g. a cross-robot predicate over two traces). |

### `_timestamp`

| | |
|---|---|
| **Type** | `float` (seconds since Unix epoch) |
| **Source** | Converter copies `DataRecord.timestamp`. |
| **Read by framework** | No, but read by **verdict services**: `ThresholdVerdict` uses it for the `sustain_sec` window; emitted verdicts use it as `Verdict.timestamp`. Falls back to `time.time()` if absent. |
| **Purpose** | Time correlation and sustained-violation windows. |

### `_source_name`

| | |
|---|---|
| **Type** | `string` |
| **Source** | Converter copies `DataRecord.source_name` (or a synthetic name such as `"fleet"` for aggregating converters). |
| **Read by framework** | No (convention only). |
| **Purpose** | Diagnostics / source attribution inside the verdict service. |

### `_property_id`

| | |
|---|---|
| **Type** | `string` |
| **Source** | Converter, when a property id is configured. |
| **Read by framework** | No (convention only). The authoritative property id on a verdict is `Verdict.property_id`, set by the verdict service. |
| **Purpose** | Documents which monitored property this record feeds. |

> **All reserved keys are optional.** A minimal DSL record is just the domain
> payload the verdict service needs. Omitting `_session_id` /
> `_record_id` / `_input_record_ids` only means the emitted verdict carries no
> correlation back to the input.

---

## Domain Payload Keys

Everything not underscore-prefixed is the converter's projection of the input,
named for what the verdict service reads. The verdict service's configured
`field` (for `ThresholdVerdict`) must name one of these keys.

| Converter | Domain keys produced |
|---|---|
| `custom.rule_based_converter:RuleBasedConverter` | one key per `field_map` entry (e.g. `velocity`, `position_x`) |
| `custom.odom_speed_converter:OdomSpeedConverter` | `speed` |
| `custom.nav2_case1...:CmdVelSpeedConverter` | `speed` |
| `custom.fleet_distance:FleetDistanceConverter` | `distance` |
| `custom.relative_speed:RelativeSpeedConverter` | `relative_speed` |
| `custom.stale_watchdog:StaleWatchdogConverter` | `silent_sec` (self-scheduled) |

---

## Correlation Summary

How a DSL record becomes a correlated `Verdict` (see `_attach_correlation`,
`monitor/verdict.py`):

| DSL record key | Becomes `Verdict` field | Rule |
|---|---|---|
| `_session_id` | `monitor_session_id` | Copied if the verdict left it empty. |
| `_input_record_ids` | `input_record_ids` | Copied if present (preferred). |
| `_record_id` | `input_record_ids` | `[_record_id]` if `_input_record_ids` absent. |

`Verdict.verifier_session_id` is **not** taken from the DSL record; it is the
runner's own session id. See [datarecord_spec.md](datarecord_spec.md) for the
upstream `record_id` format.

---

## Serialization and Transport

| Path | Serialization |
|---|---|
| In-process (`monitor_node`, `node_runner`) | None — the dict object is passed directly to the verdict stage. |
| dsl `file` endpoint (archive or cross-host link) | `DslRecordFileExporter` writes one JSON line per record; `DslRecordFileSource` parses lines back with `json.loads` (optionally tailing with `follow: true`). |
| dsl `mqtt` endpoint (cross-host link) | `DslRecordMQTTExporter` publishes `json.dumps(record, default=str, ensure_ascii=False)`; `DslRecordMQTTSource` parses it back with `json.loads` into a dict. |

Implications for cross-host splits:

- The DSL record **must be JSON-serializable** at the top level — use a `dict`
  (or list/scalar). Non-native values (datetimes, custom objects) are coerced
  to strings by `default=str`, which may not round-trip to the original type;
  emit JSON-native values from the converter when the verdict service needs to
  read them back.
- Tuples become arrays, dict keys become strings, etc. (standard JSON
  semantics).
- One MQTT topic (or file) carries one link's records; give each dsl output a
  distinct `topic`/`path` so every verdict stage receives only its own records.

---

## Examples

### 1. Single-input threshold record (`OdomSpeedConverter`)

```json
{
  "speed": 0.4,
  "_source_name": "/odom",
  "_session_id": "20260415_211500_a1b2c3d4",
  "_record_id": "20260415_211500_a1b2c3d4:topic:/odom:-:7",
  "_timestamp": 1776283880.63,
  "_property_id": "odom_speed_limit"
}
```

### 2. Multi-input record (`FleetDistanceConverter`)

```json
{
  "distance": 0.8,
  "_source_name": "fleet",
  "_timestamp": 1776283880.70,
  "_input_record_ids": [
    "…:topic:/robot1/odom:-:11",
    "…:topic:/robot2/odom:-:9"
  ]
}
```

### 3. Resulting `Verdict` (after `_attach_correlation`)

For example 1, a violation verdict carries the propagated correlation:

```json
{
  "timestamp": 1776283880.63,
  "property_id": "odom_speed_limit",
  "result": false,
  "details": {"field": "speed", "op": ">", "threshold": 0.30, "value": 0.4},
  "monitor_session_id": "20260415_211500_a1b2c3d4",
  "input_record_ids": ["20260415_211500_a1b2c3d4:topic:/odom:-:7"]
}
```

---

## Authoring a converter/verdict pair

1. In `convert()`, return a `dict` of the domain keys the verdict service
   reads, plus the reserved keys you can fill from the `DataRecord`
   (`_session_id`, `_record_id`, `_timestamp`).
2. Keep values JSON-native if the pair may be split across hosts.
3. In `evaluate()`, guard with `isinstance(dsl_record, dict)` and read your
   domain keys; use `_timestamp` for any time logic.

See `custom/rule_based_converter.py` + `custom/threshold_verdict.py` for the
reference pair, and `docs/dsl_adaptation_guide.md` for the full procedure.
