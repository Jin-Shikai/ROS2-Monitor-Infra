# Specification: Map from Monitor Config to Deployment

> One config schema → many deployment shapes. This document specifies which YAML sub-trees turn on which deployment artifacts, hosts, and communication links. It is the textual counterpart to the UML deployment diagram and the bridge between the *Specification & Plugins* column of the architecture view and the *Deployment* column.

## 1. Schema recap (relevant top-level keys)

```yaml
monitor:                # MonitorNode global parameters
  output_dir: ...
  session_id_prefix: ...

topics: [...]           # ROS 2 topic subscriptions
services: [...]         # ROS 2 service introspection
actions: [...]          # ROS 2 action feedback / status

exporters: [...]        # Global DataRecord exporters (file, mqtt, custom)
converters: [...]       # DSL chains: converter → verdict → verdict-exporters

verdict_runner:         # Optional, consumed only by verdict_runner.py
  broker: ...
  topic_filter: ...
```

Each subtree contributes to a *deployment delta* — additional artifacts, processes, hosts, and links. The deltas compose; the final deployment is the union of activated deltas.

## 2. Deployment deltas

### Δ-0 — Baseline (always present)

| Element | Kind | Host |
|---|---|---|
| `MonitorNode` | `«executionEnvironment»` Python process | Edge / Robot host |
| `ROS 2 Application` | `«executionEnvironment»` Python/C++ ROS 2 nodes | Edge / Robot host |
| DDS link | `«DDS»` localhost / host network | Edge ↔ Edge |

Trigger: presence of any `topics:`, `services:`, or `actions:` entry. Docker invocation requires `network_mode: host` and a matching `ROS_DOMAIN_ID`.

### Δ-1 — Local JSONL persistence

| Element | Kind | Host |
|---|---|---|
| `FileExporter` | artifact deployed on `MonitorNode` | Edge |
| `<session_id>.jsonl` | `«artifact»` on a mounted volume | Edge filesystem |

Trigger:
```yaml
exporters:
  - type: file
```
or a per-source `exporters:` block.

### Δ-2 — MQTT egress for raw DataRecords

| Element | Kind | Host |
|---|---|---|
| `MQTTExporter` | artifact deployed on `MonitorNode` | Edge |
| `MQTT Broker` | `«executionEnvironment»` Mosquitto / EMQX | Cloud (or LAN) |
| MQTT link | `«MQTT»` (TCP/TLS, paho v2) | Edge → Broker |

Trigger:
```yaml
exporters:
  - type: mqtt
    broker: <host>
    port: 1883
    topic_prefix: monitor/
```
Effect: spawns the cloud-side Broker node in the deployment diagram. Topic naming: `monitor/<source_type>/<source_name>` (e.g. `monitor/topic/cmd_vel`).

### Δ-3 — In-process verdict evaluation (edge)

| Element | Kind | Host |
|---|---|---|
| `ConverterExporter` + `VerdictService` | artifact deployed on `MonitorNode` | Edge |
| `verdicts_<session_id>.jsonl` | `«artifact»` | Edge filesystem |

Trigger:
```yaml
converters:
  - type: custom.x:MyConverter
    inputs: ["/cmd_vel"]
    verdict:
      type: custom.x:MyVerdict
      exporters: [{ type: file }]
```
No `verdict_runner:` block ⇒ verdicts evaluated **inside** `MonitorNode`. Lowest-latency mode; uses only the edge host.

### Δ-4 — Off-board verdict evaluation (cloud)

| Element | Kind | Host |
|---|---|---|
| `VerdictRunner` | `«executionEnvironment»` standalone Python process (no rclpy) | Cloud / separate edge box |
| `MQTTSource` | artifact deployed on `VerdictRunner` | same |
| Verdict file / `VerdictMQTTExporter` | artifacts on `VerdictRunner` | same |

Trigger:
```yaml
verdict_runner:
  broker: <broker_host>
  topic_filter: monitor/#
converters: [ ... ]              # same chains as Δ-3
```
Effect: the `converters:` chains are *not* instantiated in `MonitorNode`; instead the `MonitorNode` only publishes raw DataRecords to MQTT (Δ-2) and the `VerdictRunner` process subscribes and runs the chains. Enables horizontal scaling (multiple `VerdictRunner` instances per converter, stateless).

### Δ-5 — Cloud verdict bus

| Element | Kind | Host |
|---|---|---|
| `VerdictMQTTExporter` | artifact on whichever host runs the converter chain (Δ-3 or Δ-4) | Edge or Cloud |
| Verdict topic on `MQTT Broker` | logical artifact | Cloud |

Trigger:
```yaml
verdict:
  exporters:
    - type: mqtt
      broker: <host>
      topic: verdicts/robot1/<property_id>
```
Effect: verdicts become broker-published events that any dashboard / sink can subscribe to.

### Δ-6 — Cloud persistence and dashboards (planned)

| Element | Kind | Status |
|---|---|---|
| `Database` (InfluxDB / Postgres + Timescale) | `«executionEnvironment»` on Cloud | `«planned»` |
| `Dashboards` (Grafana / web) | `«executionEnvironment»` on Cloud | `«planned»` |
| `Offline Replay` | `«executionEnvironment»` on Cloud | `«planned»` — design slot; replays JSONL via the same `Dispatcher`/converter chains |

Trigger: not config-driven yet; activated when the deployment includes the cloud DB/dashboard stack alongside the Broker. The `DataRecord` JSONL spec is already invariant across online (DDS-fed) and offline (file-fed) paths, so the replay engine reuses the existing converter / verdict plugins unchanged.

### Δ-7 — Feedback / intervention (planned)

| Element | Kind | Status |
|---|---|---|
| `Feedback Bridge` | `«executionEnvironment»` rclpy process on Edge | `«planned»` |
| Inputs | MQTT subscription to a control topic (e.g. `commands/robot1/#`) | `«planned»` |
| Outputs to ROS 2 | `«ROS 2 service»`, `«ROS 2 param»`, `«ROS 2 publish»`, `«lifecycle»` | `«planned»` |

Trigger: not yet exposed in config; design slot reserved. The Bridge runs alongside `MonitorNode` on the edge host (rclpy required), subscribes to verdict-driven or operator-driven control messages from the broker, and writes them onto the appropriate ROS 2 control surface.

## 3. Deployment shapes (config presets)

| Preset | Config sketch | Deployment shape |
|---|---|---|
| **P1 — Local-only** | `exporters: [{type: file}]`; no `converters`, no `verdict_runner` | Single host (Edge). Δ-0, Δ-1 only. |
| **P2 — Local + in-process RV** | `exporters: [{type: file}]`; `converters: [ ... ]` with `verdict.exporters: [{type: file}]` | Single host. Δ-0, Δ-1, Δ-3. |
| **P3 — Edge-acquire + cloud-evaluate** | `exporters: [{type: mqtt, ...}]`; `converters: [ ... ]`; `verdict_runner: { ... }` | Two hosts (Edge + Cloud). Δ-0, Δ-2, Δ-4. |
| **P4 — Full cloud stack** | P3 + `verdict.exporters: [{type: mqtt, ...}]` + cloud DB / dashboards | Two hosts. Δ-0, Δ-2, Δ-4, Δ-5, Δ-6. |
| **P5 — Closed-loop (planned)** | P4 + Feedback Bridge | Two hosts + intervention link. Δ-0, Δ-2, Δ-4, Δ-5, Δ-6, Δ-7. |

P1–P4 are achievable with the current code. P5 is the final-form target.

## 4. Sanity rules

- **DDS scope.** `MonitorNode` *must* share the DDS domain with the ROS 2 application. In Docker, this means `network_mode: host` + matching `ROS_DOMAIN_ID`. The deployment diagram draws this as a single `«device»` ringing both `«executionEnvironment»` boxes.
- **rclpy locality.** Only `MonitorNode` (and the planned `Feedback Bridge`) require rclpy. `VerdictRunner`, DSL engines, exporters, dashboards, and the replay engine do not — they are pure Python / TCP services and can be deployed anywhere reachable by MQTT.
- **Stateful vs stateless processes.** `MonitorNode` is stateful w.r.t. DDS discovery and per-source sequence counters; `VerdictRunner` is stateful per converter chain but stateless across chains, so it scales horizontally by spawning one process per chain or per partition of converters.
- **Failure isolation.** Each exporter on a `Dispatcher[T]` is wrapped in try/except; a broker outage does not halt the file path, and an MQTT exporter failure on the edge does not crash the converter pipeline.
