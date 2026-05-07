# DSL Layer — Extension Notes & TODOs

Scope: design notes for evolving the DataConverter / VerdictService /
verdict-sink layer. Captures what already works today, the open
extensibility gaps, and a reproducible playbook for adding new DSL
backends. Updated 2026-05-07 (post-Phase 4).

---

## 1. What already works today

| Capability | Status | Touchpoint |
|------------|--------|------------|
| Custom DataConverter (any DSL input shape) | ✅ | Subclass `DataConverter` in [monitor/converter.py](../monitor/converter.py); load via `module.path:ClassName` |
| Custom VerdictService (any DSL engine) | ✅ | Subclass `VerdictService` in [monitor/verdict.py](../monitor/verdict.py); load via `module.path:ClassName` |
| Multi-chain (one converter chain per `converters:` entry) | ✅ | `MonitorNode.__init__` iterates `config.converters`, attaches one `ConverterExporter` per spec |
| Verdict serialization (JSON) | ✅ | `Verdict.to_json()` |
| Persisted verdict file | ✅ | `FileVerdictSink`, opt-in via `verdict.output:` YAML key |
| Stdout fallback when no sink configured | ✅ | `_default_sink` in `verdict.py` |
| Session-bookend filtering at converter entrance | ✅ | `ConverterExporter.export` skips `_type != "data"` |

---

## 2. TODO 1: Pluggable verdict sinks (parity with Exporters)

### Problem statement

Today the verdict output target is hardcoded to "either stdout or one
file". The YAML key `verdict.output:` is interpreted only as a file
path. To send verdicts to MQTT / Prometheus / Slack / a dashboard, you
must edit `pipeline.build_converter_chain` and `verdict.py`. This is
asymmetric with the exporter layer, which already supports a registry of
transports (`file`, `mqtt`, …).

### Proposed design

Mirror the `Exporter` / `Dispatcher` pattern at the verdict-sink layer.

```
              VerdictService.evaluate(dsl_record) → Verdict
                                  ↓
                            VerdictExporter
                                  ↓
                          SinkDispatcher (new) ── fan-out:
                            ├── FileSink      → verdicts_*.jsonl
                            ├── MQTTSink      → broker topic
                            ├── StdoutSink    → print
                            └── ...           (user-pluggable)
```

### YAML schema (proposed)

Replace single `output:` string with a list of sink specs:

```yaml
verdict:
  type: custom.threshold_verdict:ThresholdVerdict
  property_id: cmd_vel_speed_limit
  field: speed
  op: ">"
  threshold: 0.30
  sinks:
    - type: file
      path: verdicts_{session_id}.jsonl
    - type: mqtt
      broker: localhost
      port: 1883
      topic: verdicts/robot1/cmd_vel_speed_limit
      qos: 1
    - type: stdout
```

Backward compatibility: keep `output: <path>` as syntactic sugar for
`sinks: [{type: file, path: <path>}]`.

### Implementation sketch

New file `monitor/verdict_sinks.py`:

```python
from abc import ABC, abstractmethod
from verdict import Verdict

class VerdictSink(ABC):
    @abstractmethod
    def __call__(self, verdict: Verdict) -> None: ...
    def close(self) -> None: pass


class FileSink(VerdictSink):
    """Migrate FileVerdictSink here verbatim, rename for symmetry."""
    ...


class StdoutSink(VerdictSink):
    def __call__(self, verdict): print(f"[Verdict] {verdict.to_json()}", flush=True)


class MQTTSink(VerdictSink):
    """Reuse the same paho v2 client pattern as MQTTExporter; publish
    verdict.to_json() to the configured topic. Connection management,
    bookkeeping, and no-paho fallback identical to MQTTExporter."""
    ...


VERDICT_SINK_REGISTRY: dict[str, type[VerdictSink]] = {
    "file": FileSink,
    "stdout": StdoutSink,
    "mqtt": MQTTSink,
}


def resolve_sink_class(spec: str) -> type[VerdictSink]:
    """Like resolve_converter_class — supports both built-in registry
    names and 'module.path:ClassName' for user-defined sinks."""
    if ":" in spec:
        # user-defined sink class
        ...
    return VERDICT_SINK_REGISTRY[spec]
```

Modified `monitor/pipeline.py`:

```python
def build_converter_chain(spec, output_dir, session_id, logger):
    ...
    sink_specs = verdict_spec.get("sinks") or _legacy_output_to_sinks(verdict_spec)
    sinks = []
    for s in sink_specs:
        sink_cls = resolve_sink_class(s["type"])
        sink_kwargs = {k: v for k, v in s.items() if k != "type"}
        # path-template substitution for any {session_id} placeholders
        sink_kwargs = _substitute_session_id(sink_kwargs, session_id, output_dir)
        sinks.append(sink_cls(**sink_kwargs))

    if len(sinks) == 1:
        verdict_exporter = VerdictExporter(verdict_service, sink=sinks[0])
    else:
        verdict_exporter = VerdictExporter(
            verdict_service,
            sink=lambda v: [s(v) for s in sinks],   # fan-out
        )
    ...
```

(A cleaner alternative: a `MultiSink` callable wrapping a list — keeps
fan-out logic out of `pipeline.py`.)

### Edge cases / open questions

- **Sink failure isolation**: today `FileVerdictSink` swallows nothing
  (writes are wrapped in lock + flush, exceptions propagate). Should
  multi-sink fan-out catch per-sink to keep the others alive? Probably
  yes — mirror `Dispatcher.dispatch`'s try/except.
- **Path templating**: `{session_id}` is currently substituted in
  `pipeline.build_converter_chain`. Move that to a sink helper so all
  sinks (mqtt topic name, file path, slack channel, …) get the same
  treatment.
- **Cleanup on SIGINT**: `verdict_runner` and `MonitorNode.shutdown`
  currently iterate `_verdict_sinks` and call `close()`. Multi-sink
  fan-out must keep that list complete.
- **Backpressure**: MQTTSink inherits paho's queue semantics, same as
  MQTTExporter. Document the same drop-on-overflow caveat.

---

## 3. TODO 2: User-defined sink classes via `module.path:ClassName`

Once the registry pattern lands, the same `module.path:ClassName`
loader used for converters/verdicts should also work for sinks. So
users can ship a `custom.my_slack_sink:SlackSink` without touching the
framework. The registry holds built-ins; anything with `:` in it is
loaded via `importlib`.

This is a 1-line change in `resolve_sink_class` once TODO 1 is in place.

---

## 4. Reference: Custom DSL integration playbook

For any new DSL backend, the integration is always 4 steps. Captured
here so future contributors don't have to re-derive it.

### Step 1 — Subclass `DataConverter`

```python
from data_record import DataRecord
from converter import DataConverter

class MyDSLConverter(DataConverter):
    name = "MyDSLConverter"

    def __init__(self, ...):
        # YAML keys flow into __init__ kwargs verbatim
        ...

    def convert(self, record: DataRecord):
        # Translate DataRecord into whatever shape your DSL engine wants.
        # Return None to drop the record (wrong source, missing field, ...)
        # Return any object — dict / dataclass / tuple / your own type.
        # Convention: include "_timestamp" in the dict so downstream
        # state machines can reason about time.
        ...
```

### Step 2 — Subclass `VerdictService`

```python
from verdict import Verdict, VerdictService

class MyDSLVerdict(VerdictService):
    name = "MyDSLVerdict"

    def __init__(self, ...):
        ...

    def evaluate(self, dsl_record):
        # Whatever your DSL engine does. Return:
        #   None     → silent (no Verdict emitted)
        #   Verdict  → fires the sink
        # Convention: edge-trigger (one Verdict per state transition),
        # not level-trigger (one per breaching record), to keep output
        # volume bounded.
        ...
```

### Step 3 — Drop the files into an importable path

Anywhere on `sys.path` will do. The existing convention is `custom/`
at the project root, which `monitor_node.py` and `verdict_runner.py`
both prepend to `sys.path` at startup. Place an `__init__.py` next to
your modules.

### Step 4 — Wire up in YAML

```yaml
converters:
  - type: custom.my_dsl_converter:MyDSLConverter
    # converter __init__ kwargs go here, sibling to `type`
    foo: bar
    property_id: my_property
    verdict:
      type: custom.my_dsl_verdict:MyDSLVerdict
      property_id: my_property
      # verdict __init__ kwargs go here
      output: verdicts_{session_id}.jsonl
```

### Framework-imposed contract (the only constraints)

1. Converter must be a subclass of `DataConverter`; Verdict must be a
   subclass of `VerdictService`. `resolve_converter_class` /
   `resolve_verdict_class` enforce this via `issubclass`.
2. Return-type conventions:
   - Converter `None` → record is dropped silently
   - Verdict `None` → silent
   - Verdict returning a `Verdict` object → sink invoked
3. Converter and Verdict privately agree on `dsl_record` shape. No
   `DSLRecord` base class is imposed by the framework — duck typing.

### DSL → suggested implementation mapping

| DSL family | Converter shape | Verdict internals | Notes |
|------------|-----------------|--------------------|-------|
| Threshold / SLO | `dict` of named fields + `_timestamp` | direct comparison + edge-trigger | already shipped: `RuleBasedConverter` + `ThresholdVerdict` |
| Sliding-window / STL | same dict shape | internal `deque[(ts, value)]`, evict by age, evaluate window predicate | new code; window state lives inside the verdict |
| Counting / occurrence | same dict shape | counter inside verdict, fire when count > N | trivial; demonstrates non-threshold pattern |
| LTL on atomic propositions | `(ts, frozenset[str])` of true propositions | external library (e.g. Spot Büchi automaton) — feed it the trace one event at a time | converter responsible for evaluating each proposition's truth value |
| Trajectory / geometric | list of `(ts, x, y, theta)` tuples | accumulate buffer; check geometric predicate (within tube, distance to plan, …) | useful for Nav2 case study |
| State machine / regime detection | discrete event tag string | maintain a state machine inside verdict, fire on illegal transitions | good fit for action-status records |

---

## 5. Out of scope / non-goals (deliberate)

- **Generic DSL parser**: the framework will never parse user-supplied
  LTL/STL strings. That belongs to the verdict implementation.
- **Cross-converter coordination**: each chain is independent. If you
  need a property that spans two streams, write one converter that
  reads the second stream's state via shared mutable state at the
  module level. The framework will not bind chains together.
- **Verdict storage querying**: jsonl files are the boundary. Any
  query/dashboard layer reads those externally.

---

## 6. Suggested implementation order

1. **TODO 1 — pluggable verdict sinks**: highest leverage, well-scoped
   (~150 LOC + tests). Unlocks MQTT verdict streaming for live
   dashboards.
2. **TODO 2 — user sink classes**: trivial follow-up, ~10 LOC.
3. Then defer further DSL playbook examples (sliding window, LTL) to
   when an actual case study demands them — premature implementation
   risks codifying the wrong abstraction.
