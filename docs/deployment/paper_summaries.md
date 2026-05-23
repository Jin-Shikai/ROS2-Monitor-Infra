# Per-Paper Technical Summaries (verified from PDFs)

> Source PDFs live under `docs/*.pdf`. The summaries below were extracted from the full text of each paper (figures, tables, algorithm boxes, experimental sections). Each subsection answers the same set of questions so the comparison in `capability_comparison.md` can be defended line-by-line.

---

## 1. ROSMonitoring (Ferrando et al., TAROS 2020)

### Identity
Ferrando, Cardoso, Fisher (Liverpool) + Ancona, Franceschini, Mascardi (Genova). *ROSMonitoring: a Runtime Verification Framework for ROS.* TAROS 2020, Springer LNCS 12228, pp. 387–399.

### Problem & contributions
ROSRV is tied to ROS Groovy and MOP. ROSMonitoring (1) is **portable across multiple ROS distributions** (Melodic, Kinetic) and (2) **agnostic w.r.t. specification formalism**; (3) YAML-driven instrumentation that auto-generates Python monitor nodes; (4) decouples the oracle over WebSocket+JSON; (5) ships two reference oracles (RML, Reelay).

### Architecture & components
Three parts: **Instrumentation** (rewrites `.launch` files by inserting `<remap from="X" to="X_mon"/>` and emits `monitor.py`), **Monitor** (auto-generated Python ROS node that subscribes to the remapped topic, JSON-encodes via `rospy_message_converter`, optionally calls the oracle, then republishes onto the original topic name), and **Oracle** (external WebSocket server, returns a JSON verdict). Sequential per-monitor communication preserves ordering.

### DSL
**Formalism-agnostic via Oracle.** RML default (SWI-Prolog, rewriting-based trace expressions) or Reelay (header-only C++, LTL/MTL/STL with past operators). Example: `left_speed matches { topic: 'wheels_control', direction: 'left', speed: val } with val <= 10;`. Both online and offline supported.

### Data path
**Topics only.** Services, actions, parameters, lifecycle, tf, logs **not supported**. Authors: "ROSMonitoring can only monitor messages that are sent through topics." Full message payload visible. No QoS handling.

### Verdict & feedback
Boolean / oracle-dependent. On verdict: publishes `monitor_error` warning topic with originating topic, payload, violated property, ROS time. **`filter` action drops violating messages** ("does not propagate the message"); oracle may **rewrite payload contents**. No service calls / no lifecycle / no params.

### Evaluation
Curiosity Mars rover (Gazebo): forward/back speed ≤ 15, turn ≤ 10. Scalability: 10 nodes × 10 topics; at 100 Hz transparent; at 500 Hz, single monitor 270 % overhead, 10 monitors 9 %; at 1000 Hz/topic saturates even with 10 monitors. Delay < 1 ms at 100 Hz.

### Maturity & limitations
Python monitor, Prolog/C++ oracles. **ROS 1 only.** Open source: [github.com/autonomy-and-verification-uol/ROSMonitoring](https://github.com/autonomy-and-verification-uol/ROSMonitoring). Limits: topic-only; sequential oracle is the bottleneck; high-frequency saturation; no head-to-head vs ROSRV.

---

## 2. ROSMonitoring 2.0 (Ghaffari Saadat et al., FMAS 2024)

### Identity
Ghaffari Saadat, Dennis, Fisher (Manchester) + Ferrando (Modena). *ROSMonitoring 2.0: Extending ROS Runtime Verification to Services and Ordered Topics.* FMAS 2024, EPTCS 411, pp. 38–55. doi:10.4204/EPTCS.411.3.

### Problem & contributions
Two v1 gaps: (a) services unsupported; (b) cross-topic ordering reflects subscriber-receive order, not publication order. Contributions: (1) **service monitoring** with full intermediary semantics (monitor is server-to-client and client-to-server); (2) **publication-time reordering algorithm** with per-topic timestamp buffers, plus Lemma 1 + Theorem 1 of correctness; (3) **partial ROS 2 port** (service monitoring only, no reordering yet); (4) UAV Battery Supervisor case study.

### Architecture & components
Same as v1 architecturally. Service interception (Fig. 3): Client → `callService(req,res)` → Monitor → `sendRequest` → Oracle → if OK, forward to Server, receive `response(res)`, send to Oracle again, then to Client; on violation, `publishError()` and bypass. Reordering: `buffer` dict per topic, `messages` dict per publication timestamp; release the message with smallest timestamp once every buffer is non-empty; WebSocket call serialized via locks.

### DSL
Still formalism-agnostic. Examples in **Past MTL via Reelay**. E.g., Property 1a: `forall[i]. (forall[s]. {topic: "/battery_status", id: *i, status: *s} → once({topic: "/input_accepted", id: *i}) and once({topic: "/battery_percentage", id: *i, percentage: *s}))`. **Three-valued verdicts** (⊤, ⊥, ?, with ?⊤ / ?⊥).

### Data path
**Topics + Services**; actions explicitly future work. Assumption 1: same-topic messages arrive in publication order. Reordering merges across topics by timestamp. Deadlock risk explicitly analyzed; workarounds: split publishing/service logic, fold ordered fields into other messages.

### Verdict & feedback
Three-valued. **Drops messages**; **bypasses service invocation** on violation; substitutes error response to client. No lifecycle / param manipulation claimed.

### Evaluation
UAV Battery Supervisor (Battery 25 Hz, Supervisor 10 Hz, LED Panel 35 Hz, ROS 1 Noetic). Without ordering: frequent **false negatives**. With ordering: accurate verdicts; round-trip time substantially higher at status-change events.

### Maturity & limitations
ROS 1 Noetic full; **ROS 2 partial (services only, no reordering).** [github.com/autonomy-and-verification-uol/ROSMonitoring](https://github.com/autonomy-and-verification-uol/ROSMonitoring) (`ros2` branch). Limits: ordering deadlocks, latency overhead, ROS 2 port incomplete, no actions, no buffer timeouts, no head-to-head benchmark.

---

## 3. ROMoSu (Stadler & Vierhauser, RoSE 2023)

### Identity
Stadler, Vierhauser (LIT SCS Lab, JKU Linz). *ROMoSu: Flexible Runtime Monitoring Support for ROS-based Applications.* RoSE 2023 @ ICSE.

### Problem & contributions
Setting up monitoring has high upfront cost; configs must evolve with the system. Six challenges (C1–C6). Contributions: (1) flexible monitoring framework architecture; (2) prototype (Angular + Django + SQLite + InfluxDB + Mosquitto MQTT + Esper CEP + `roslibpy`); (3) evaluation on three use cases — simulated TurtleBot 3 (GTB), physical TurtleBot 3 (HTB), simulated OpenMANIPULATOR-X (GMX); (4) up to **95.48 % event-volume reduction** vs brute-force monitoring.

### Architecture & components
Four parts (Fig. 1): **Framework Core** (Connection Interface, API Adapter, Config-DB SQLite, ROS Adaptation Manager, Runtime Cache, **ROS Connector via `roslibpy`**, Runtime Data Broker = **Mosquitto MQTT**); **Admin UI** (Angular wizard); **Dashboard** (Monitoring Supervisor + Data Explorer); **External Services** (Runtime Data Persistence = InfluxDB in Docker; Runtime Data Validation = **Esper CEP** in Java). Two phases: Configuration (CT) and Monitoring Data Collection (MT). **No source modification, no topic remapping** — uses `roslibpy` / `rosbridge` to subscribe non-invasively.

### DSL
**Framework itself has no property DSL.** Constraint checking delegated to **Esper CEP** (EPL); supports static value checks (S) and temporal checks (T) such as 10 s windowed average. Configurations entered via a GUI wizard.

### Data path
**Topics only**, via `roslibpy`. Sub-topic selection, per-topic adaptive frequency sampling, multi-namespace. No services / actions / params / lifecycle. Single-event + windowed via Esper.

### Verdict & feedback
Boolean violation events surfaced on Dashboard; persisted in InfluxDB. **Purely passive — no closed-loop feedback into ROS.**

### Evaluation
GTB/HTB/GMX, 3 runs × 3 min. Metrics: **RTT** (ROS arrival → MQTT broker) and **EPT** (effective processing time). Avg EPT 0.27 ms. RTT dominated by ROS native publish rates. Event reduction up to 95.48 %.

### Maturity & limitations
Angular + Django + SQLite + InfluxDB + Mosquitto + roslibpy + Esper. Authors commit to open-sourcing but no URL in the preprint. **ROS 1 (tested with TurtleBot 3 + Gazebo); no ROS 2 claim.** Limits: usability untested; limited topics/constraints in eval; no adaptive runtime reconfiguration; no native DSL.

---

## 4. Monitoring ROS2 (Perez et al., FMAS+AVoCS 2022)

### Identity
Perez, Mavridou, Pressburger, Will, Martin (KBR/NASA Ames + VCU). *Monitoring ROS2: from Requirements to Autonomous Robots.* FMAS+AVoCS 2022, EPTCS 371, pp. 208–216.

### Problem & contributions
Hand-written ROS 2 monitors are error-prone and the plumbing is repetitive. Contribution: workflow **FRET → Ogma → Copilot → C99 → ROS 2 wrapper package** (CMake + package.xml + node sources). The novel piece is **Ogma's new ROS 2 backend**.

### Architecture & components
- **FRET**: FRETISH (6-field structured NL) → past- and future-time **MTL** → Lustre / SMV.
- **Ogma**: emits Copilot stream specs and the ROS 2 wrapper package.
- **Copilot**: stream DSL → hard real-time **C99** with `step()` and user-supplied `handler<prop>()`.
- **Wrapper**: monitoring node subscribes to input topics, calls `step()`, fires handler on violation; logging node forwards to ROS 2 default logger. Variable→topic→type mapping file required.

### DSL
**FRETISH (fixed for users)** compiled to **past-time MTL**. Toolchain is layered (Copilot is the IR). Online, single-step. Example: condition `persisted(10, current_consumption > cc_t & wind_speed > ws_t)`, timing `within 10 seconds`, response `current_consumption <= cc_t`.

### Data path
**Topics only.** No services / actions / params / lifecycle / tf / logs. Single-message handler.

### Verdict & feedback
**Boolean.** On violation: publishes an **empty message** on `copilot/handler<propname>` ("presence indicates a violation"). Forwarded to ROS 2 default logger. **No filtering, no enforcement** — explicitly: "In contrast to ROSMonitoring, we do not provide message filtering capabilities."

### Evaluation
**None quantitative.** UAM/quadrotor "sustained high wind, high current" is *motivating*, not benchmarked.

### Maturity & limitations
Generated C99 + C++ wrapper. Branch of [github.com/nasa/ogma](https://github.com/nasa/ogma). ROS 2 (distro unspecified). Limits: all monitors re-run on every input; empty violation messages (no values/timestamps); no probabilistic specs; only on-arrival evaluation policy; no enforcement.

---

## 5. ros2_tracing (Bédard, Lütkebohle, Dagenais — RA-L 2022)

### Identity
Bédard (Polytechnique Montréal) + Lütkebohle (Bosch Corporate Research) + Dagenais (Polytechnique Montréal). *ros2_tracing: Multipurpose Low-Overhead Framework for Real-Time Tracing of ROS 2.* IEEE RA-L 7(3):6511–6518, 2022. arXiv:2201.00393v4.

### Problem & contributions
rosbag and logs are too coarse / too perturbing. Prior ROS-1/2 tracing tools have high overhead or narrow scope. Contributions: (1) **extensible multi-aspect ROS 2 instrumentation** (messages, callbacks, services, executor states, lifecycle); (2) **two-phase init/runtime instrumentation design** for low overhead; (3) combined ROS 2 + OS (kernel) trace analyses; integration with `ros2 launch` / `ros2 trace`.

### Architecture & components
**tracetools** indirection lib called by core ROS 2 packages; tracepoints fire into **LTTng** (default, ~158 ns/userspace event). Instrumented in **rclcpp / rcl / rmw** (no rclpy). Output: **CTF (Common Trace Format)**. Analysis: `tracetools_analysis` (Python) + Eclipse Trace Compass. Test utilities: `tracetools_test`, `tracetools_read`.

### DSL
**None — instrumentation only.** Classified as "I" not "M" by authors. Properties live in user analysis scripts. **Offline-first**; LTTng live mode is a future path to online.

### Data path
Pub/sub, callbacks, executors, lifecycle, init events. **Services only at init**; **actions, params, tf, logs** not instrumented. **DDS middleware not instrumented.** **rclpy not instrumented.** Two-phase split keeps hot-path payload small (handle/id only).

### Verdict & feedback
**Not applicable.** Trace events only. No verdict, no feedback.

### Evaluation
60-min `performance_test` runs, FastDDS, PREEMPT_RT, i7-3770. **Mean end-to-end latency overhead 0.0033 ms** (all tracepoints enabled); 50 % between 0.0010 and 0.0056 ms. Vs ROS-FM 15–515 % CPU, RAPLET 2–20 % latency, ROS-Llama 30–40 % CPU.

### Maturity & limitations
Maintained, upstream in ROS 2 core. C/C++ + Python. ROS 2 **Rolling**. Linux-only (LTTng). Source: [github.com/ros2/ros2_tracing](https://github.com/ros2/ros2_tracing). Limits: no services/actions instrumentation (only init); no object-destruction tracepoints; no DDS; no rclpy; offline-first; no native multi-host orchestration.

---

## 6. RTAMT (Yamaguchi, Hoxha, Ničković — STTT 2025; extends ATVA 2020)

### Identity
Yamaguchi (Toyota TRINA) + Hoxha + Ničković (AIT). *RTAMT — Runtime Robustness Monitors with Application to CPS and Robotics.* STTT (accepted); arXiv:2501.18608v1.

### Problem & contributions
CPS/robotics V&V needs both qualitative + quantitative STL monitoring, online + offline, discrete + dense time, integrated with ROS and MATLAB/Simulink. Contributions: (1) Python library API + integrations (**ROS via `rtamt4ros`**, **Simulink Level 2 S-functions**); (2) **Interface-Aware STL (IA-STL)** with input/output classification → **output robustness** and **input vacuity**; (3) extensible to new operators/semantics; (4) Python + **C++ backend** (Boost.Python).

### Architecture & components
Class diagram (Fig. 5): syntax layer (ANTLR4 lexer/parser, `StlAst`, `StlAstVisitor`, `StlPastifier`); semantic layer (`TimeInterpreter` with discrete + dense subclasses; `AbstractOfflineInterpreter.evaluate`, `AbstractOnlineInterpreter.update`); C++ backend via Boost.Python. Spec classes: `StlDenseTimeOfflineSpecification`, `StlDenseTimeOnlineSpecification`, `StlDiscreteTimeOnlineSpecificationCpp`. **ROS integration**: a single Python monitor node using `rospy` introspection to dynamically create subscribers/publishers per variable. Topic mapping via spec annotations:
```
@topic(req, rtamt/req)
@topic(rob, rtamt/rob)
rob.value = G[0,10]((req.value>=3) -> (F[0,5](gnt.value>=3)))
```

### DSL
**STL** (bfSTL bounded-future, pSTL past-only, IA-STL). Operators U, S, F, G, X, O, H, Y, ↑, ↓. **Pluggable** via Section 5 of the paper (add lexer/parser rules + visitor overrides). Online uses **pastification** automatically.

### Data path
**Topics only.** Reads message payload fields (only int/long/float real-valued). Discrete-time monitor periodic (`set_sampling_period`); dense-time event-driven with piecewise-constant interpolation. No QoS.

### Verdict & feedback
**Quantitative real-valued robustness ρ(φ,w,t).** IA-STL adds output robustness μ and input vacuity ν (±∞ for vacuous). Robustness published on a ROS topic (e.g. `rtamt/rob`). **No enforcement** built in; downstream nodes may use the robustness signal. Used externally for falsification testing (Simulink) and sensitivity analysis.

### Evaluation
Scaling vs # samples and formula complexity. **C++ ~10× faster** than Python; even slowest case ≈ 0.5 ms/sample (dense-time Python). HSR (Toyota Human Support Robot) in ROS + Gazebo with assume-guarantee fault localization. Simulink AECS falsification case study.

### Maturity & limitations
Maintained tool, PyPI. Python + C++. [github.com/nickovic/rtamt](https://github.com/nickovic/rtamt) + [rtamt4ros](https://github.com/nickovic/rtamt4ros). Supports ROS (ROS 1 implied by `rosrun`; ROS 2 also claimed). Limits: dense-time treated as perfect continuous clock; no decentralized/distributed monitors; only float/int/long; only periodic pub/sub assumed.

---

## 7. Digital-Twin Enabled RV (Betzer, Boudjadar, Frasheri, Talasila — arXiv 2024)

### Identity
Betzer, Boudjadar, Frasheri, Talasila (Aarhus University). *Digital Twin Enabled Runtime Verification for Autonomous Mobile Robots under Uncertainty.* arXiv:2412.09913v1, Dec 2024.

### Problem & contributions
AMRs face sensor/floor uncertainty causing divergence between wheel-expected and ground-actual speed; on-robot verification is too expensive. Contribution: **cloud-located executable Digital Twin** hosting **TeSSLa-synthesized monitors** that validate *proposed* actuations before execution and can **override** them. Reported **41 % MSE reduction** in actual-vs-expected speed.

### Architecture & components
- **Physical Twin**: Turtlebot 3 Burger with Raspberry Pi, 360° Lidar, hector SLAM (chosen over gmapping because it doesn't false-report movement when wheels slip).
- **Digital Twin (cloud)**: Catalogue of DT Assets (monitors, behaviors, models, simulators, operations, data).
- **Bus**: **MQTT broker** (`test.mosquitto.org:1883` in the demo) bidirectional between PT and DT. InfluxDB for persistence/replay.
- **Telegraf** + custom **TeSSLa Telegraf Connector** that compiles the TeSSLa spec into a **Rust** program; Rust talks to Telegraf via **UDP**.
- **Workflow** (Fig. 2): Sense → Analyze (propose actuation, don't execute) → MQTT → DT runs monitors → Validate (T/F + adjusted speed) → MQTT → robot Executes if approved, else re-Senses.

### DSL
**TeSSLa** stream-based RV. Three properties: P1 braking distance (∀i, Bdist ≤ Ldist), P2 tolerance (∀i, |expected − actual| ≤ δ), P3 Lidar validation (∀i,j, |lⱼ − lⱼ±1| ≤ γ). TeSSLa example shows boolean verdict plus adjusted `expectedSpeed`. **Online, stream-based.**

### Data path
**ROS topics bridged out to MQTT.** Custom Lidar ROS message defined as two arrays for CSV mock replay. Monitor sees full payload (360 Lidar floats, expected/actual speeds). No services / actions / params / lifecycle.

### Verdict & feedback
**Boolean per property + derived corrective action** (proportional gain 0.5, capped at T3B max 0.22 m/s). **Closed-loop enforcement**: DT can **block** an actuation (robot will not execute, re-senses) and **override** by sending adjusted speed.

### Evaluation
T3B on a bumpy yoga mat, speeds 0.015 → 0.1 m/s. Default: robot gets stuck twice. With DT monitor: recovers via augmented commands. **MSE 0.0017 (default) → 0.0010 (augmented) = 41 % improvement**. No CPU/latency overhead numbers; only P2 evaluated end-to-end.

### Maturity & limitations
Research prototype. TeSSLa → Rust via Telegraf Connector; Python orchestration. Hector SLAM, gmapping, InfluxDB, Telegraf, Mosquitto. **ROS 1 (implicit via Turtlebot 3 stack)**. No open-source link in the preprint. Limits: P1/P3 specified but not evaluated; DT only validates robot-proposed actuations, not compute them; synchronization latency between robot and DT not analyzed.
