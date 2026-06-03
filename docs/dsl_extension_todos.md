# DSL Layer — Extension Notes & TODOs

Scope: design notes for evolving the DataConverter / VerdictService /
verdict-output layer. Captures what already works today, the open
extensibility gaps, and a reproducible playbook for adding new DSL
backends. Updated 2026-05-12 (TODO 1 design revised to unify around the
existing `Exporter[T]` hierarchy — see Section 2). Updated 2026-05-12
again to finish the unification: `sink` terminology gone, `Dispatcher`
now IS-A `Exporter[T]`, and the verdict-runner's inbound transport is
pluggable via a `Source` registry symmetric to verdict-side exporters
(§9).

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

## 2. TODO 1: Pluggable verdict outputs (unified with `Exporter[T]`)

### Problem statement

Today the verdict output target is hardcoded to "either stdout or one
file". The YAML key `verdict.output:` is interpreted only as a file
path. To send verdicts to MQTT / Prometheus / Slack / a ROS2 topic / a
socket, you must edit `pipeline.build_converter_chain` and `verdict.py`.
This is asymmetric with the upstream exporter layer, which already
supports a registry of transports (`file`, `mqtt`, …).

### Design decision: do **not** invent a second "Sink" hierarchy

An earlier draft of this TODO proposed mirroring the exporter layer
with a parallel `VerdictSink` / `SinkDispatcher` stack. That is
duplication — `Exporter[T]` in [monitor/exporter.py](../monitor/exporter.py)
is already a generic transport interface and `Dispatcher[T]` already
provides fan-out + per-exporter try/except isolation + a registry.
`VerdictExporter` in [monitor/verdict.py](../monitor/verdict.py) is
itself an `Exporter[Any]`. The orphan `FileVerdictSink` (also in
`verdict.py`) is the only thing that doesn't fit the pattern — it
should be replaced by an `Exporter[Verdict]`, not propagated.

So the chosen direction is **one term, one hierarchy**:

```
Exporter[T]                       # already exists, generic over payload type
   ├── FileExporter[T]            # already exists, works for any T (uses to_json or json.dumps)
   ├── StdoutExporter[T]          # new, ~5 LOC, generic
   ├── MQTTExporter               # already exists, DataRecord-specific topic naming
   ├── VerdictMQTTExporter        # new, Verdict-specific (single topic)
   ├── ROS2TopicExporter[Verdict] # future, user-pluggable
   └── any user-defined exporter  # loaded via `module.path:ClassName`
```

Anything a user might want to send a Verdict to — ROS2 topic, Unix
socket, gRPC stream, Slack webhook, Kafka — is just an `Exporter[Verdict]`
subclass. No new base class, no parallel registry, no extra terminology.

### YAML schema

Replace the single `output:` string with a list under `exporters:`,
matching the spelling used at the top level for DataRecord exporters:

```yaml
verdict:
  type: custom.threshold_verdict:ThresholdVerdict
  property_id: cmd_vel_speed_limit
  field: speed
  op: ">"
  threshold: 0.30
  exporters:
    - type: file
      path: verdicts_{session_id}.jsonl
    - type: mqtt
      broker: localhost
      port: 1883
      topic: verdicts/robot1/cmd_vel_speed_limit
      qos: 1
    - type: stdout
    - type: my_pkg.custom_exporter:SlackVerdictExporter
      webhook: https://hooks.slack.com/...
```

Only the `exporters:` list is accepted. There is no legacy `output:`
sugar — every verdict sink is declared as one entry in `exporters:`.

### Implementation sketch

New file `monitor/verdict_exporters.py`:

```python
from exporter import Exporter
from verdict import Verdict

class VerdictFileExporter(Exporter[Verdict]):
    """Append each Verdict as one JSON line to `path`."""
    def __init__(self, path: str): ...

class VerdictStdoutExporter(Exporter[Verdict]):
    def export(self, v): print(f"[Verdict] {v.to_json()}", flush=True)

class VerdictMQTTExporter(Exporter[Verdict]):
    """Paho v2 client publishing each verdict to a single topic.
    Mirrors exporter_mqtt.MQTTExporter's connection lifecycle and
    no-paho fallback. (Future: extract a shared MQTTClientHandle if a
    third caller appears.)"""
    def __init__(self, broker, port, topic, qos=1, ...): ...

VERDICT_EXPORTER_REGISTRY: dict[str, type[Exporter[Verdict]]] = {
    "file":   VerdictFileExporter,
    "stdout": VerdictStdoutExporter,
    "mqtt":   VerdictMQTTExporter,
}

def resolve_verdict_exporter_class(type_str: str) -> type[Exporter[Verdict]]:
    if ":" in type_str:
        cls = _import_class(type_str)
        if not (isinstance(cls, type) and issubclass(cls, Exporter)):
            raise TypeError(...)
        return cls
    return VERDICT_EXPORTER_REGISTRY[type_str]
```

`pipeline.build_converter_chain` is updated to:

1. Read `verdict.exporters: [...]`.
2. For each spec, resolve the class and instantiate with the spec's
   kwargs (minus `type:`), substituting `{session_id}` in any string
   value.
3. Build a `Dispatcher[Verdict]` and `.add()` each instantiated
   exporter. Fan-out + per-exporter try/except is inherited from the
   existing `Dispatcher` implementation — no new code.
4. Wire `VerdictExporter(service, sink=verdict_dispatcher.dispatch)`.
5. Return `(ConverterExporter, Dispatcher[Verdict])` so the caller
   can close all verdict-side exporters on shutdown.

### What goes away

- `FileVerdictSink` (class in `verdict.py`) — replaced by
  `VerdictFileExporter`.
- The ad-hoc `list[FileVerdictSink]` tracked in `MonitorNode` and
  `verdict_runner` — replaced by a `list[Dispatcher[Verdict]]`,
  which uses the same `close_all()` already used for upstream
  exporters.

### Edge cases handled by reusing `Dispatcher`

- **Per-exporter failure isolation**: already in `Dispatcher.dispatch`
  (try/except per exporter). No extra code needed.
- **Shutdown cleanup**: `Dispatcher.close_all()` already iterates and
  swallows exceptions per-exporter.
- **Path templating**: a single `_substitute_session_id` helper in
  `pipeline.py` applies to *all* string kwargs (so MQTT topic names,
  file paths, Slack channels, etc. all get the same treatment).
- **Backpressure for MQTT**: `VerdictMQTTExporter` inherits paho's
  queue semantics (drop-on-overflow), same caveat as `MQTTExporter`.

---

## 3. TODO 2: User-defined exporter classes via `module.path:ClassName`

Already covered by TODO 1's `resolve_verdict_exporter_class`: any spec
with `:` in the `type:` is loaded via `importlib` and validated as an
`Exporter` subclass. So a user can ship
`my_pkg.custom_exporter:SlackVerdictExporter` (or a ROS2-topic
exporter, or a socket exporter) without touching the framework.

This was a 1-line concern in the earlier "parallel Sink hierarchy"
draft. Under the unified design it costs zero additional code — it
falls out of the registry resolver.

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

## 6. Status: TODO 1 + TODO 2 landed (2026-05-12)

Implemented in this branch. Summary of what changed:

### New code

- [monitor/verdict_exporters.py](../monitor/verdict_exporters.py) — three
  built-in `Exporter[Verdict]` classes plus the registry + resolver:
  - `VerdictFileExporter(path, flush_every=1)`
  - `VerdictStdoutExporter()`
  - `VerdictMQTTExporter(topic, broker, port, qos, ...)` — paho v2 client,
    bounded queue, no-paho fallback, externally-injectable `client=` for
    unit tests, mirrors `exporter_mqtt.MQTTExporter` semantics.
  - `VERDICT_EXPORTER_REGISTRY` + `resolve_verdict_exporter_class()`
    (handles both registry names and `module.path:ClassName`).
- [monitor/exporter.py](../monitor/exporter.py) — added generic
  `StdoutExporter[T]` so the same primitive is available for any payload
  type (used by `VerdictStdoutExporter`; future DataRecord stdout exporter
  can reuse it as-is).

### Refactored

- [monitor/verdict.py](../monitor/verdict.py) — `FileVerdictSink`
  removed. `VerdictExporter` unchanged in interface; its docstring now
  describes the new `Dispatcher[Verdict]` wiring.
- [monitor/pipeline.py](../monitor/pipeline.py) —
  `build_converter_chain` now returns `(ConverterExporter, Dispatcher[Verdict])`.
  Parses `verdict.exporters: [...]`. Recursive
  `{session_id}` substitution is applied to every string kwarg, so MQTT
  topics, file paths, Slack channels, etc. all get the same templating.
  Relative `path` kwargs resolve against `monitor.output_dir`.
- [monitor/monitor_node.py](../monitor/monitor_node.py) and
  [monitor/verdict_runner.py](../monitor/verdict_runner.py) — replaced
  the `list[FileVerdictSink]` shutdown bookkeeping with
  `list[Dispatcher[Verdict]]`, calling `close_all()` on each.
- [monitor/config.yaml](../monitor/config.yaml) — shows the new
  `exporters:` schema, with `mqtt` and `stdout` examples commented out.

### Tests (now 104 passing, up from 92)

- [test/unit/test_verdict.py](../test/unit/test_verdict.py) —
  `FileVerdictSink` tests removed.
- [test/unit/test_verdict_exporters.py](../test/unit/test_verdict_exporters.py) —
  new file, 12 tests covering all three built-ins, the registry, the
  `module:Class` loader, and a user-defined `Exporter[Verdict]` subclass.
- [test/unit/test_pipeline.py](../test/unit/test_pipeline.py) — updated
  to the new return tuple shape; added coverage for the multi-exporter
  schema and unknown-type failure.

### What the user-facing change buys you

- **MQTT verdict streaming**: enable by uncommenting the `mqtt` block in
  `config.yaml`. The exporter publishes each verdict as a JSON line to
  one topic; a live dashboard can subscribe directly.
- **Multiple sinks per property**: file + stdout + MQTT simultaneously,
  with per-exporter try/except so one broken transport doesn't kill the
  rest (inherited from `Dispatcher`).
- **User-defined transports**: a `ROS2TopicExporter`, `SocketExporter`,
  `SlackVerdictExporter`, ... is just an `Exporter[Verdict]` subclass
  living under `custom/` (or any importable path), referenced in YAML
  by `type: module.path:ClassName`. Zero framework code touched.
- **No new term to learn**: everything is an Exporter. The "Sink" word
  is gone from the codebase.

### Deferred to future work (intentionally)

- **DRY the paho MQTT plumbing**: `VerdictMQTTExporter` duplicates ~30
  lines of paho client lifecycle from `MQTTExporter`. Worth extracting
  to a shared `MQTTPublisher` helper once a third caller appears, not
  before.
- **Generic `MQTTExporter[T]`**: would let one class serve both record
  types via a topic-naming strategy callback. Same answer — wait for a
  third user.
- **ROS2TopicExporter as a built-in**: keep it as a user-pluggable
  example in `custom/` for now; promote to built-in only if the Nav2
  case study uses it persistently.

---

## 7. Status: TODO 3 landed (per-source exporters, 2026-05-12)

Implemented in the same session as TODO 1/2. Every `topics:`,
`services:`, and `actions:` entry now accepts an optional `exporters:`
block; when present, records from that source go *only* to that
dispatcher's exporters (isolated from the global `exporters:` list).

### What changed

- [monitor/monitor_node.py](../monitor/monitor_node.py):
  - `_build_dispatcher` gained a `source_name` parameter; `file`
    exporters get a default `filename_suffix` derived from the source
    name when one isn't given (e.g. `/cmd_vel` → `_cmd_vel`).
  - New `MonitorNode._dispatch_for(spec, source_name, log)` returns a
    tee callable: feeds the source's records to either a per-source
    dispatcher (if the spec has its own `exporters:`) or the global
    dispatcher, **and** always to a dedicated `_converter_dispatcher`
    so DSL converter chains keep seeing every data record regardless
    of where exporters route it.
  - Converter chains were moved off the global dispatcher onto the new
    `_converter_dispatcher` tap, decoupling "where data is stored"
    from "what evaluates the data".
  - All three `_register_topic/_register_service/_register_action`
    methods use `_dispatch_for` for the collector's dispatch hook.
  - `shutdown` closes the new converter and per-source dispatchers.
- [test/Nav2_case1/config_case1.yaml](../test/Nav2_case1/config_case1.yaml):
  added a worked example — `/cmd_vel` carries its own per-source
  `exporters:` block, writing to `<output_dir>/<session>_cmd_vel.jsonl`.
- [test/unit/test_monitor_node_service_discovery.py](../test/unit/test_monitor_node_service_discovery.py):
  test fixtures updated for the new attributes.

### YAML shape

```yaml
exporters:                       # global default (used by sources without
  - type: file                   #  their own exporters:)

topics:
  - name: /odom                  # no exporters: here → uses global
    transformers: [...]

  - name: /cmd_vel
    transformers: [...]
    exporters:                   # per-source: REPLACES the global stream
      - type: file               # filename suffix auto-derived as _cmd_vel
      - type: mqtt
        topic_prefix: monitor/cmdvel/
```

### Semantics chosen (and why)

- **Per-source `exporters:` replaces the global one** for that source
  — not "in addition". Rationale: the common case is "I want this
  topic in its own file", and additive semantics force the user to
  always also delete the global `file` exporter or accept duplicate
  writes.
- **Converter chains are unaffected**: a tee dispatch sends every data
  record to the converter tap on the side, independent of per-source
  exporter routing. This is why `/cmd_vel` can have its own file
  exporter *and* its existing DSL verdict chain in case1.
- **Session bookends bypass per-source dispatch** — only the global
  dispatcher publishes them. Converters skip bookends anyway
  (`record._type != "data"` check in `ConverterExporter`).

---

## 8. Status: TODO 4 landed (converter `inputs:` filter, 2026-05-12)

Implemented in the same session. Each converter spec now accepts an
optional `inputs: [source_name, ...]` list that the framework uses to
drop records from other sources before the converter sees them — so
custom converters can stay pure projection logic and skip the
`if record.source_name != "/cmd_vel": return None` boilerplate.

### What changed

- [monitor/pipeline.py](../monitor/pipeline.py):
  - New `_SourceFilteredExporter` wrapping a `ConverterExporter` with
    an allowed-source set; checks `record.source_name` before forwarding.
  - `build_converter_chain` reads `inputs:` from the spec, validates it
    (non-empty list of strings), and wraps the ConverterExporter when
    set. Missing/None `inputs:` preserves the old "see all sources"
    behaviour.
  - Return type widened to `tuple[Exporter, Dispatcher]`.
- [custom/nav2_case1/cmd_vel_speed_converter.py](../custom/nav2_case1/cmd_vel_speed_converter.py):
  source-name check removed; framework now handles it.
- [test/Nav2_case1/config_case1.yaml](../test/Nav2_case1/config_case1.yaml):
  the converter entry now carries `inputs: ["/cmd_vel"]`.
- [test/unit/test_pipeline.py](../test/unit/test_pipeline.py): added
  three tests (positive filtering, empty-list rejected,
  wrong-type rejected).

### YAML shape

```yaml
converters:
  - type: custom.nav2_case1.cmd_vel_speed_converter:CmdVelSpeedConverter
    inputs: ["/cmd_vel"]              # framework filter (optional)
    verdict:
      type: ...
      exporters: [...]
```

### Why `inputs:` is by source-name, not by exporter-name

An earlier design idea was to give each Exporter a unique YAML name and
let each converter declare an "input exporter" name. That doesn't match
the data flow: Exporters are *sinks* (write file / publish MQTT);
converters consume records from the same Dispatcher tap that feeds the
exporters, not from the exporters themselves. The unique identifier
that already exists at the framework level — and that the user
naturally writes anyway — is the source name (`/cmd_vel`, `/odom`,
`/navigate_to_pose`). So `inputs:` matches against those. If a future
need arises to reference "the same paho client as the global MQTT
exporter" or similar, a named-Exporter table can be added then.

---

## 9. Status: TODO 5 landed (pluggable verdict-runner Source + final unification, 2026-05-12)

Two cleanups, done together because they're the same idea applied to
opposite ends of the chain:

### 9a. `sink` terminology removed; `Dispatcher` is now an `Exporter[T]`

The earlier round of work removed `FileVerdictSink` and the "Sink" base
class, but `verdict.py` still had a `sink: Callable` parameter on
`VerdictExporter` plus a `_default_sink` helper, and `Source.start(sink)`
took a callable on the inbound side. The framework now uses exactly one
term — `Exporter` — end to end.

- [monitor/exporter.py](../monitor/exporter.py) — `Dispatcher` now
  subclasses `Exporter[T]`. Its fan-out loop is the `export` method;
  `dispatch = export` is kept as an alias so the existing
  `dispatcher.dispatch(record)` call sites stay grammatical. This is what
  lets a Dispatcher be handed to any consumer that expects an
  `Exporter[T]` (VerdictExporter downstream, Source upstream).
- [monitor/verdict.py](../monitor/verdict.py) — `VerdictExporter`
  constructor parameter is now `exporter: Exporter[Verdict] | None`.
  Default is a `StdoutExporter[Verdict](label="Verdict")`. Calls
  `self.exporter.export(verdict)`. `_default_sink` deleted.
- [monitor/source.py](../monitor/source.py) — `Source.start(exporter: Exporter[T])`.
  No more `Callable` indirection.
- [monitor/source_mqtt.py](../monitor/source_mqtt.py) —
  `self._exporter: Exporter[DataRecord]`, calls `.export()`.
- [monitor/pipeline.py](../monitor/pipeline.py) —
  `VerdictExporter(verdict_service, exporter=verdict_dispatcher)` instead
  of `sink=verdict_dispatcher.dispatch`.

### 9b. Verdict-runner ingestion is pluggable via a `Source` registry

Previously the verdict-runner hardcoded `MQTTSource(...)` directly, with
broker/port/topic_filter/qos baked into `RunnerConfig` as MQTT-specific
fields. That made MQTT a privileged transport rather than one option among
many — out of step with the symmetric story on the verdict-output side.

- [monitor/sources.py](../monitor/sources.py) — new file. `SOURCE_REGISTRY`
  maps short names (`mqtt`) to `Source` subclasses; `resolve_source_class`
  also accepts `module.path:ClassName` for user-defined sources. Same
  shape as `verdict_exporters.resolve_verdict_exporter_class`.
- [monitor/verdict_runner.py](../monitor/verdict_runner.py) — `RunnerConfig`
  now carries a single `source: dict` (`{type, **kwargs}`). `main()`
  resolves the class via the registry, instantiates with the remaining
  kwargs, and calls `source.start(raw_dispatcher)` directly (Dispatcher
  is an Exporter now).
- [monitor/config.yaml](../monitor/config.yaml) — `verdict_runner:` now
  uses the nested `source:` schema.

### YAML shape

```yaml
verdict_runner:
  source:
    type: mqtt                 # or 'module.path:ClassName' for user-defined
    broker: localhost
    port: 1883
    topic_filter: monitor/#
    qos: 1
```

A user-defined replay-from-file or UDP-socket source is one
`Source[DataRecord]` subclass plus one line of YAML — no framework
changes. Symmetric to how verdict-side exporters work.

### Tests (now 112 passing, up from 107)

- [test/unit/test_verdict.py](../test/unit/test_verdict.py) — updated
  `VerdictExporter` constructor calls to `exporter=` and switched test
  doubles to small `Exporter[Verdict]` classes.
- [test/unit/test_source_mqtt.py](../test/unit/test_source_mqtt.py) —
  same migration for `MQTTSource.start(...)`.
- [test/unit/test_sources.py](../test/unit/test_sources.py) — new file,
  5 tests for registry + `module:Class` loader + bad-type rejection.

### Why this matters for the framework story

The system boundary is now exactly `Source → Dispatcher → Exporter`
(with `ConverterExporter`/`VerdictExporter` as adapters that fit inside
this same vocabulary). Every transport — file, MQTT, ROS2 topic, UDP,
gRPC — is an `Exporter[T]` on the outbound side and a `Source[T]` on the
inbound side, both pluggable, both selected from YAML, both resolvable
via `module.path:ClassName` for user code. There is no second hierarchy
to learn.

---

## 10. Suggested next work

1. ~~**TODO 1 — pluggable verdict outputs**~~ ✅ landed 2026-05-12.
2. ~~**TODO 2 — user exporter classes**~~ ✅ subsumed by TODO 1.
3. ~~**TODO 3 — per-source exporters**~~ ✅ landed 2026-05-12.
4. ~~**TODO 4 — converter `inputs:` filter**~~ ✅ landed 2026-05-12.
5. ~~**TODO 5 — `sink` unification + pluggable verdict-runner Source**~~
   ✅ landed 2026-05-12.
6. **TODO 6 — example custom transports** under `custom/`: a
   `ROS2TopicExporter` (publishes verdicts to a `std_msgs/String`
   topic on the monitor's own node), a `SocketExporter` (UDP), and a
   matching `FileReplaySource` / `SocketSource`. Each ~30 LOC, written
   as user-pluggable demos rather than built-ins. Promote to built-in
   only if the Nav2 case study consistently uses them.
7. **Phase 5 — TurtleBot3 / Nav2 case study**: drive a real Nav2 stack
   into the monitor, validate that a meaningful property fires, decide
   on the basis of that experience whether sliding-window / LTL /
   geometric DSL backends are worth implementing. The
   `custom/nav2_case1/` package (this branch) is the seed.
8. **Sliding-window / LTL / trajectory DSL examples**: deferred until
   a case study demands them — premature implementation risks
   codifying the wrong abstraction. When the time comes, each will be
   one or two files under `custom/<case>/` following the same one-
   property-per-package layout as `nav2_case1`.

### Explicitly dropped

- *Generic `Exporter[T]` MQTT publisher / shared `MQTTPublisher` helper.*
  The earlier draft of this section listed extracting a paho client
  helper shared by `MQTTExporter` and `VerdictMQTTExporter`. Dropping
  it: the duplication is ~30 lines of well-understood lifecycle code,
  the two classes will likely keep diverging (publish-many-topics vs
  publish-one-topic semantics), and a premature shared helper would
  couple them. Revisit only if a third paho-publishing class appears.
