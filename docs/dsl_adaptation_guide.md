# Adapting a New DSL

This document is the normative procedure for connecting a new property
language or runtime-verification engine to ROS2-Monitor-Infra. The historical
design discussion remains in `dsl_extension_todos.md`.

## Integration Boundary

The framework does not parse a DSL formula itself. A DSL adapter is a pair:

```text
DataRecord -> DataConverter -> DSL record -> VerdictService -> Verdict
```

- `DataConverter` translates generic monitored ROS2 records into the input
  representation expected by the DSL engine.
- `VerdictService` owns the DSL engine or monitor state, consumes DSL records,
  and emits the framework's common `Verdict` object.
- YAML selects and parameterizes both classes.

## Required Inputs Before Adaptation

1. Define the monitored property and its verdict meaning.
2. List required ROS2 observations: source names, message types, and field
   paths.
3. Define the DSL-record schema passed between converter and verdict service.
4. Decide whether the property is local, multi-source, or cross-robot.
5. Decide whether evaluation runs in `monitor_node` or a remote
   `verdict_runner`.

## Adaptation Procedure

### 1. Implement the converter

Create an importable class derived from `monitor/converter.py:DataConverter`.
The class must implement:

```python
def convert(self, record: DataRecord) -> dsl_record | None:
    ...
```

Return `None` for irrelevant or incomplete records. Include `_timestamp`,
`_record_id`, `_session_id`, and, for multi-input properties,
`_input_record_ids` where possible so verdict evidence remains traceable.

For multi-source properties, one converter may retain the latest state from
multiple source names and emit only after all required inputs exist. See
`custom/fleet_distance.py`.

### 2. Implement the verdict service

Create an importable class derived from `monitor/verdict.py:VerdictService`.
It must implement:

```python
def evaluate(self, dsl_record) -> Verdict | None:
    ...
```

Return `None` when no externally visible verdict should be emitted. Return a
`Verdict` when the property state should be reported. The existing examples
are edge-triggered: they emit once on violation and once on recovery.

An external DSL engine may be instantiated and called inside this class. Its
formula syntax, automaton, temporal window, and internal state remain private
to the adapter.

### 3. Make the adapter importable

Place the modules under `custom/<dsl_or_case>/` with `__init__.py`, or install
them as a Python package available on `PYTHONPATH`. YAML plugin types use:

```text
module.path:ClassName
```

No registry edit is required for converters or verdict services.

### 4. Add runtime YAML

```yaml
topics:
  - name: /required_source
    type: package/msg/Message
    transformers:
      - type: FieldExtractor
        fields: [field.required.by.dsl]

converters:
  - type: custom.my_dsl.converter:MyDSLConverter
    inputs: [/required_source]
    formula: "dsl-specific formula or identifier"
    verdict:
      type: custom.my_dsl.verdict:MyDSLVerdict
      property_id: my_property
      exporters:
        - type: stdout
        - type: file
          path: "my_property_{session_id}.jsonl"
```

Keys beside converter `type`, except framework-reserved `inputs`, `output`,
and `verdict`, become converter constructor keyword arguments. Keys beside
verdict `type`, except `exporters`, become verdict constructor keyword
arguments.

### 5. Choose deployment transport

- Integrated/local: put `topics` and `converters` in one monitor config.
- Remote/central: robot config exports DataRecords through MQTT; verifier
  config declares `verdict_runner.source` and the converter chain.
- Offline: recorder writes DataRecords to file; verifier uses source `file`.
- Choreographed: local verdicts use an MQTT verdict exporter; an aggregator
  uses `custom.verdict_mqtt_source:VerdictMQTTSource`.

The DSL adapter itself should remain unchanged when only deployment changes.

### 6. Test the adapter

At minimum, test:

1. converter accepts the intended source and fields;
2. converter drops unrelated or incomplete records;
3. evidence record ids propagate into verdicts;
4. verdict fires for a violating trace;
5. verdict reports recovery or the DSL's intended positive result;
6. YAML class paths and constructor arguments build successfully;
7. one self-contained demo produces both expected verdict states.

## Acceptance Checklist

- The property and DSL-record contract are documented.
- Constructor fields, defaults, and allowed values are documented.
- The adapter does not depend on a deployment-specific transport.
- Every required ROS2 field is collected or can be discovered.
- Verdicts have stable `property_id` values and evidence identifiers.
- Unit tests and one end-to-end demo pass.

## Current Limitations

- There is no generic DSL parser or formula validator.
- There is no machine-readable plugin capability manifest.
- The converter and verdict service agree on DSL-record shape by convention.
- Cross-converter coordination is not provided by the framework.
- Automatic configuration generation requires the user to select the custom
  package and ROS2 resources explicitly. A package manifest can expose the
  adapter class references and constructor arguments without asking the
  generator to understand the property's business semantics.
