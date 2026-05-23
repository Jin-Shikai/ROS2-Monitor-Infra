# Capability Comparison: ROS2-Monitor-Infra vs. Related Work

> Scope: seven peer-reviewed / preprint frameworks whose PDFs were read end-to-end (`docs/*.pdf`, summarized in `paper_summaries.md`), plus four secondary references (ROSRV, RMoM, Kirca et al., Caldas et al.) from the literature survey.
>
> Comparison axes — beyond deployment topology — cover **functionality** (what the system can monitor and react to), **implementation** (how it is built), **features** (DSLs, semantics, performance), and **distinguishing characteristics**. Each cell can be traced to the corresponding section of `paper_summaries.md`.
>
> Symbols: ● yes / first-class · ◐ partial · ○ no · — N/A.

---

## 1. Functionality — what the system can do

### 1.1 Supported ROS primitives

| System | ROS ver. | Topics | Services | Actions | Params | Lifecycle | Tf | Kernel events |
|---|---|---|---|---|---|---|---|---|
| ROSMonitoring (TAROS'20) | ROS 1 | ● | ○ | ○ | ○ | ○ | ○ | ○ |
| ROSMonitoring 2.0 (FMAS'24) | ROS 1 + partial ROS 2 | ● | ● | ○ (future) | ○ | ○ | ○ | ○ |
| ROMoSu (RoSE'23) | ROS 1 | ● | ○ | ○ | ○ | ○ | ○ | ○ |
| Monitoring ROS 2 (FMAS'22) | ROS 2 | ● | ○ | ○ | ○ | ○ | ○ | ○ |
| ros2_tracing (RA-L'22) | ROS 2 | ● pub/sub events | ◐ init only | ○ | ○ | ● transitions | ○ | ● via LTTng |
| RTAMT / rtamt4ros (STTT'25) | ROS 1/2 | ● | ○ | ○ | ○ | ○ | ○ | ○ |
| Digital-Twin RV (arXiv'24) | ROS 1 | ● (via MQTT bridge) | ○ | ○ | ○ | ○ | ○ | ○ |
| **ROS2-Monitor-Infra** | **ROS 2** | ● | ● *(introspection events)* | ● *(feedback + status; goal/result deferred)* | ◐ *(read for `«planned»` feedback)* | ◐ *(planned feedback channel)* | ○ | ○ |

> Coverage of services + actions side-by-side is unique to this project among ROS 2 frameworks. Only ROSMonitoring 2.0 also covers services, and its ROS 2 port is partial (services only, no reordering, no actions).

### 1.2 Feedback / closed-loop intervention

| System | Drop / filter msg | Rewrite payload | Block service | Pub ROS msg | Call ROS service | Update param | Lifecycle transition | Actuation override |
|---|---|---|---|---|---|---|---|---|
| ROSMonitoring | ● `filter` action | ● via oracle | ○ | ● `monitor_error` warning | ○ | ○ | ○ | ○ |
| ROSMonitoring 2.0 | ● | ● | ● bypass + error response | ● `/verdict` | ○ | ○ | ○ | ○ |
| ROMoSu | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ |
| Monitoring ROS 2 | ○ "we do not provide filtering" | ○ | ○ | ● empty handler topic | ○ | ○ | ○ | ○ |
| ros2_tracing | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ |
| RTAMT | ○ | ○ | ○ | ● robustness signal | ○ | ○ | ○ | ○ (used externally for falsification) |
| Digital-Twin RV | ● (re-sense) | ● adjusted speed | ○ | ● actuation command | ○ | ○ | ○ | ● |
| **ROS2-Monitor-Infra** | ○ *(passive by design)* | ○ | ◐ `«planned»` | ◐ `«planned»` | ◐ `«planned»` | ◐ `«planned»` | ◐ `«planned»` | ◐ `«planned»` |

> The **scope** of the planned feedback surface (params + services + lifecycle + pubs) is broader than any single surveyed system. ROSRV / ROSMonitoring achieve enforcement only at the message bus; Digital-Twin RV intervenes only via actuation overrides. None of the seven targets the ROS 2 lifecycle FSM or parameter API as feedback channels.

### 1.3 Property specification surface

| System | Formalism | Online | Offline | Robustness (quant.) | Three-valued | Past | Future | Windowed |
|---|---|---|---|---|---|---|---|---|
| ROSMonitoring | RML default, Reelay (LTL/MTL/STL past) | ● | ● | ◐ via Reelay | ○ | ● | ◐ | ● |
| ROSMonitoring 2.0 | RML / Past MTL via Reelay | ● | ● | ◐ via Reelay | ● ⊤/⊥/?⊤/?⊥ | ● | ○ | ● |
| ROMoSu | Esper CEP (EPL) — *no native DSL* | ● | ◐ | ○ | ○ | ● | ○ | ● (e.g. 10 s avg) |
| Monitoring ROS 2 | FRETISH → past-time MTL → Copilot | ● | ○ | ○ | ○ | ● | ○ via pastification | ● |
| ros2_tracing | none — user analysis scripts | ○ live mode (future) | ● | — | — | — | — | — |
| RTAMT | STL (bfSTL, pSTL, IA-STL) | ● | ● | ● ρ, μ output, ν vacuity | ○ | ● | ● via pastification | ● |
| Digital-Twin RV | TeSSLa | ● | ◐ replay | ○ | ○ | ● | ● | ● |
| **ROS2-Monitor-Infra** | **DSL-agnostic plug-in bus** (any engine implementing `VerdictService`) | ● | ● *(same plugins on JSONL replay)* | ◐ *(engine's choice)* | ◐ *(engine's choice)* | ◐ | ◐ | ◐ |

> Every other framework is bound to **one** formalism family (or two via Reelay). ROS2-Monitor-Infra is the only one where multiple engines (e.g. an RTAMT-style STL engine and an RML-style trace engine) can coexist on the same `DataRecord` stream behind a single `Dispatcher[Verdict]`. The trade-off: RTAMT ships richer STL semantics out-of-the-box; this project ships none and expects users (or vendor plugins) to bring them.

---

## 2. Implementation — how the system is built

| Axis | ROSMonitoring | ROSMonitoring 2.0 | ROMoSu | Monitoring ROS 2 | ros2_tracing | RTAMT | Digital-Twin RV | **ROS2-Monitor-Infra** |
|---|---|---|---|---|---|---|---|---|
| Monitor language | Python (generated) | Python (generated) | Python (`roslibpy`) + Java (Esper) + Angular/Django | C99 (Copilot) + C++ wrapper | C/C++ in core + Python analysis | Python + C++ (Boost.Python) | Rust (TeSSLa-compiled) + Python orchestration | Python (rclpy) |
| Instrumentation style | `.launch` topic remap | `.launch` topic remap + service intermediary | Non-invasive subscribe via `roslibpy / rosbridge` | Wrapper node | Source-level **LTTng tracepoints** in `rclcpp/rcl/rmw` | Wrapper monitor node, dynamic pub/sub via `rospy` reflection | MQTT bridge out of ROS topics | Standalone monitor container, shared `network_mode: host` for DDS |
| User input | YAML config + spec file | YAML config + spec file | GUI wizard (Angular) | FRETISH NL → mapping file | Build flags + `ros2 trace` | `.stl` text + ROS topic annotations | TeSSLa spec + Telegraf connector | YAML config + `module:Class` plugin refs |
| Property / monitor synthesis | Auto-generated `monitor.py` | Auto-generated `monitor.py` | None — config drives subscriptions | Codegen `FRET → Ogma → Copilot → C99 → ROS 2 pkg` | None | AST → interpreter, with pastification | TeSSLa → Rust via Telegraf Connector | Dynamic plugin import (`module.path:ClassName`) |
| Bus / transport | ROS topics + WebSocket+JSON (Oracle) | ROS topics + WebSocket+JSON (Oracle) + service interception | ROS via `roslibpy`; **MQTT** to external services; REST UI | ROS 2 DDS | CTF trace files via LTTng | ROS topics | ROS topics + **MQTT** (bidirectional) + UDP (Telegraf↔Rust) | ROS 2 DDS (in) + **MQTT** (out) + file (JSONL); MQTT-in for `VerdictRunner` |
| External services | RML oracle (SWI-Prolog) or Reelay (C++) | RML / Reelay | InfluxDB + Esper CEP | Copilot toolchain | LTTng, Trace Compass | C++ backend via Boost.Python | InfluxDB + Telegraf + TeSSLa toolchain | Optional: MQTT broker (Mosquitto / EMQX); user-pluggable exporters |
| Containerization | not stated | not stated | InfluxDB in Docker | not stated | Linux LTTng; built into ROS 2 core | not stated | not stated | Dockerfile + docker-compose with `network_mode: host` |
| Multi-host topology | Oracle separable via WebSocket | Same | MQTT-mediated services + UI | Single host | Single host (per-trace) | Single host | Robot + Cloud DT, MQTT-mediated | Edge `MonitorNode` + Cloud `VerdictRunner` + Broker + DB + Replay |
| Maintained / upstream | research prototype | research prototype | research prototype | research prototype | **upstream in ROS 2 core** | maintained, PyPI | research prototype | research prototype |

> A few specific implementation choices worth highlighting against the alternatives:
> - **Plugin entrypoint is `module:ClassName`** loaded at startup (Python `importlib`), not a code-generator that recompiles when properties change. The trade-off vs Monitoring ROS 2 (FRET/Ogma/Copilot): the latter produces hard-real-time C99 but requires a build step on every spec change; this project sacrifices real-time guarantees for hot-spec iteration.
> - **`DataRecord` JSONL** is the invariant interchange format on both file and MQTT. This is what lets the same `VerdictService` instance be reused unchanged for online (DDS-fed) and offline replay paths — a property none of the other frameworks have.
> - **Separation of `MonitorNode` (rclpy) and `VerdictRunner` (no rclpy)** lets the verdict engines be deployed on hosts that don't even have ROS installed. RTAMT and Monitoring ROS 2 both bake the verdict engine into a ROS node and must run wherever the ROS distro is installed.

---

## 3. Features — semantics, performance, evaluation

| Axis | ROSMonitoring | ROSMonitoring 2.0 | ROMoSu | Monitoring ROS 2 | ros2_tracing | RTAMT | Digital-Twin RV | **ROS2-Monitor-Infra** |
|---|---|---|---|---|---|---|---|---|
| Verdict type | Boolean / oracle-shaped | 3-valued + oracle | Boolean (Esper) | Boolean | none — events | Real-valued robustness (ρ, μ, ν) | Boolean + corrective action | Boolean + arbitrary `details` dict; pluggable to robustness |
| Time model | discrete (per-msg) | discrete + reordered by pub timestamp | event-time + 10 s windows | discrete | wall-clock nanosecond CTF | discrete + dense + pastification | event-time (push) | wall-clock + ROS-header time; converter decides |
| Throughput evaluation | 100/500/1000 Hz × 10 topics × 10 nodes | UAV 25/10/35 Hz | 3 systems × 3 min × 3 runs | none | 60-min `performance_test` | scaling vs sample count, formula complexity | T3B yoga-mat 0.015–0.1 m/s | qualitative: Nav2 `/cmd_vel` at 5 Hz throttle |
| Overhead reported | 270 % @ 500 Hz 1 mon → 9 % @ 10 mon | RTT spikes at status-change with ordering | EPT 0.27 ms avg | none | **0.0033 ms mean** | **C++ ≈10× Python**, ≈0.5 ms/sample worst | 41 % MSE improvement; no overhead nums | none reported yet |
| Multi-host | Oracle separable | Oracle separable | MQTT + REST UI | none | none | none | robot + cloud | edge + cloud + replay |
| Offline replay | log-then-replay | log-then-replay | InfluxDB persistence | none | **first-class (CTF)** | offline interpreter | InfluxDB mock | **same plugins on JSONL replay** |
| Visual dashboard | none | none | **Angular Dashboard** | none | Eclipse Trace Compass | Simulink blocks | InfluxDB / Grafana-style | `«planned»` |
| Open source | ● Liverpool repo | ● same repo | ◐ author commitment, no URL in preprint | ● Ogma branch | ● ros2_tracing upstream | ● nickovic repos | ○ none in preprint | ● this repo |

---

## 4. Where ROS2-Monitor-Infra has a real advantage

Combining the three matrices above, the empty cells in the prior art map to genuine differentiators:

### A. **Plug-in DSL bus, not DSL plug**
Every surveyed system fixes a formalism family (STL for RTAMT; TeSSLa for Digital-Twin RV; FRETISH/MTL for NASA Ames; RML/Past-MTL via Reelay for ROSMonitoring; Esper EPL for ROMoSu). ROS2-Monitor-Infra's `DataConverter` → `VerdictService` contract lets **multiple engines coexist on the same `DataRecord` stream behind one `Dispatcher[Verdict]`**, switched at configuration time. A user can run an STL engine on `/cmd_vel`, a trace-rewriting engine on `/diagnostics`, and a CTL model-checker on `/lifecycle_events` in the same process.

### B. **First ROS-2-native framework that covers topics + services + actions simultaneously**
Only ROSMonitoring 2.0 also addresses services, and its ROS 2 support is partial (services only, no reordering, no actions). Every other ROS-2-native system is topic-only.

### C. **Edge / cloud separation with offline replay parity**
The `DataRecord` JSONL format is invariant across:
- Online edge collection (DDS → `MonitorNode` → JSONL + MQTT),
- Online cloud evaluation (MQTT → `VerdictRunner` with no rclpy dependency),
- Offline replay (archived JSONL → same `VerdictRunner` → same verdict outputs).

ros2_tracing is offline-first; RTAMT has online + offline but only within one process; ROSMonitoring's online and offline diverge in transport. Reusing the *same plugin instances* on archive replay is unique here. This is what `Specification: map from config to deploy` (`config_to_deployment.md`) makes concrete.

### D. **MQTT as the cross-host monitor protocol, by design**
ROMoSu and Digital-Twin RV adopted MQTT in 2023+. This project adopts the same trend but separates **DDS-coupled acquisition** (edge `MonitorNode`) from **rclpy-free evaluation** (`VerdictRunner`), so a verdict server can scale horizontally on commodity hosts without a ROS distribution installed.

### E. **Broadest planned feedback surface in the corpus**
ROSRV / ROSMonitoring filter at the message bus; ROSMonitoring 2.0 adds service-call bypass; Digital-Twin RV overrides actuation; everyone else publishes a verdict topic and stops. This project's `Feedback Bridge` is designed for the **full ROS 2 control surface** — `«ROS 2 service»`, `«ROS 2 param»`, `«lifecycle»`, `«ROS 2 publish»` — currently marked `«planned»` in the deployment diagram. Honest acknowledgement of scope is itself a contribution: the diagram does not claim what the code does not implement.

### F. **Per-source isolation and stateless verdict scaling**
The dispatcher's per-source `exporters:` override + try/except per exporter + the `VerdictRunner`'s no-rclpy design mean (i) one bad sink does not crash the pipeline; (ii) one verdict chain can be partitioned across N `VerdictRunner` instances. ROSMonitoring's bottleneck — sequential per-monitor oracle calls reaching 270 % overhead at 500 Hz — is exactly the problem this design avoids by separating acquisition from evaluation across processes.

### G. **Clean UML deployment notation**
None of the surveyed papers use proper UML 2.x deployment stereotypes (`«device»`, `«executionEnvironment»`, `«artifact»`, `«deploy»`). Kirca et al. use "device" boxes and the Digital-Twin paper labels its two hosts, but neither uses the formal notation. The promotion-slide deliverable closes this presentation gap.

---

## 5. Where ROS2-Monitor-Infra is currently weaker than the prior art

Stated explicitly so the slide doesn't overclaim:

| Limitation | Best-in-class reference | Implication |
|---|---|---|
| **No quantitative robustness semantics shipped** | RTAMT (ρ, μ, ν) | A user wanting STL robustness must implement / port it via the `VerdictService` plugin. Mitigation: the plugin contract is small (one method), so an `rtamt`-backed `VerdictService` is feasible as a future contribution. |
| **No formal-method codegen path** | Monitoring ROS 2 (FRETISH → C99) | No FRET-style structured-NL editor; no compilation to hard-real-time code. Verdicts run in Python. |
| **No published throughput / overhead numbers** | ros2_tracing (0.0033 ms), ROMoSu (0.27 ms EPT) | Required before any real-time deployment claim. Mitigation: a benchmark harness mirroring `performance_test` is straightforward. |
| **No GUI / dashboard yet** | ROMoSu (Angular wizard + dashboard) | Marked `«planned»` in the deployment diagram. |
| **No closed-loop enforcement today** | ROSMonitoring (drop/rewrite), Digital-Twin RV (override) | The `«planned»` Feedback Bridge is design-only in the codebase. |
| **No formal ordering / correctness proofs** | ROSMonitoring 2.0 (Lemma 1, Theorem 1) | Edge-triggered verdict semantics are documented but not proven w.r.t. message arrival order. |
| **No published case study at the depth of RTAMT/HSR or Digital-Twin/T3B** | RTAMT (HSR fault localization), DT-RV (41 % MSE improvement) | Nav2 `/cmd_vel` example is in the repo but not yet written up as a benchmark. |

These are tractable; flagging them up front strengthens the claim of the genuine differentiators above.

---

## 6. Slide-ready bullets (refreshed)

- **One DSL-agnostic bus, not one DSL.** The only framework in the corpus where LTL / STL / CTL / trace / custom engines coexist on the same `DataRecord` stream.
- **Topics + Services + Actions, in ROS 2, in one config.** No surveyed ROS 2 system reaches this surface.
- **Edge collection (DDS) decoupled from verdict evaluation (rclpy-free).** `VerdictRunner` runs anywhere reachable by MQTT and scales horizontally without a ROS distribution.
- **Online and offline use the same plugins** because `DataRecord` JSONL is invariant across DDS, MQTT, and file paths.
- **Designed for the full ROS 2 feedback surface** — services, parameters, lifecycle, publishes — beyond the message-bus enforcement seen in ROSRV / ROSMonitoring or the actuation override seen in Digital-Twin RV. Currently `«planned»`; honestly marked in the deployment diagram.
- **First in the corpus to ship a UML 2.x deployment diagram** with `«device»`, `«executionEnvironment»`, `«artifact»`, `«deploy»` stereotypes — the artefact the professor specifically asked for.
