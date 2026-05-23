# Capability Comparison: ROS2-Monitor-Infra vs. Related Work

> Scope: 12 related works (ROS 1 + ROS 2 runtime verification / monitoring / observability), prioritising recent (2023–2025) publications. See `related_work_survey.md` for full citations and per-paper figure analysis.
>
> Method: each capability is judged on what the **deployed system** can do (not just what the paper discusses as future work). Status is reported as ●  yes, ◐ partial, ○ no, — not applicable.

## Capability Matrix

| # | Paper / System | Year | ROS&nbsp;version | Multi-host topology | Cloud component | Feedback to ROS | DSL pluggability | UML deployment notation | Property semantics |
|---|---|---|---|---|---|---|---|---|---|
| 1 | ROSRV (Huang et al.) | 2014 | ROS 1 | ○ single host | ○ | ● drop / rewrite via RVMaster | ◐ MOP / parametric specs | ○ ad-hoc | Trace properties |
| 2 | ROSMonitoring (Ferrando et al.) | 2020 | ROS 1 | ◐ Oracle separable via WebSocket | ○ | ◐ filter on renamed topics | ● formalism-agnostic Oracle | ○ ad-hoc | Default RML / Prolog |
| 3 | ROSMonitoring 2.0 | 2024 | ROS 1, partial ROS 2 | ◐ Oracle separable | ○ | ● service-request interception | ● same as v1 | ○ ad-hoc | RML + ordered services |
| 4 | ROMoSu (Stadler et al.) | 2023 | ROS 1/2 | ● ROS↔MQTT seam | ◐ MQTT broker implicit | ◐ reconfiguration only | ◐ scenario-based | ○ ad-hoc | Constraint checks |
| 5 | ros2_tracing (Bédard et al.) | 2022 / 2023 | ROS 2 | ◐ distributed in 2023 follow-up | ○ | ○ offline observability | — | ○ ad-hoc | CTF traces |
| 6 | Monitoring ROS2 / FRET-Ogma-Copilot (Perez et al.) | 2022 | ROS 2 | ○ single host | ○ | ◐ verdict topic only | ◐ FRETish → TL → C99 (one chain) | ○ ad-hoc | Temporal logic → C99 |
| 7 | RTAMT / rtamt4ros (Ničković et al.) | 2020 / 2023 / 2025 | ROS 1/2 | ○ single host | ○ | ◐ verdict topic only | ○ STL-only | ○ ad-hoc | STL (discrete + dense) |
| 8 | TeSSLa-ROS-Bridge (Kallwies et al.) | 2023 | ROS 1/2 | ○ single host | ○ | ◐ verdict topic only | ○ TeSSLa-only | ○ ad-hoc | TeSSLa stream RV |
| 9 | RV + Field Testing (Caldas et al.) | 2024 | ROS 1/2 | discussed | discussed | discussed | survey | ○ ad-hoc | Methodology |
| 10 | Digital-Twin RV (Betzer et al.) | 2024 / 2025 | ROS 2 | ● robot + cloud | ● cloud DT | ● actuation override | ○ TeSSLa-only | ◐ labelled hosts, no UML stereotypes | TeSSLa / STL-like |
| 11 | RMoM (Hu et al.) | 2019 | ROS 1 | ● swarm + verification device | ○ | ◐ per-layer verdicts | ◐ ROSMonitoring | ○ ad-hoc | Hierarchical |
| 12 | Anomaly-Detection RV (Kirca et al.) | 2023 | ROS 1 | ● 3 devices | ○ | ○ detection only | ◐ ROSMonitoring | ◐ explicit device boxes, no UML stereotypes | Security anomalies |
| ★ | **ROS2-Monitor-Infra (this project, final form)** | 2026 | ROS 2 | ● edge + cloud | ● broker + DB + dashboards + replay | ● params · services · pubs · lifecycle (planned) | ● LTL · STL · CTL · custom (single bus) | ● strict UML 2.x stereotypes | DSL-pluggable |

> "Planned" denotes capabilities that are designed-for and have reserved deployment slots in the architecture but are not yet implemented in code. They are drawn explicitly with the `«planned»` stereotype on the diagram so the contribution is honest about scope.

## Dimension-by-dimension synthesis

### 1. Multi-host topology
Most of the corpus (8 of 12) draws a single-host figure. The four works with explicit multi-host topologies are RMoM (swarm + verifier), ROMoSu (MQTT seam), Kirca et al. (3 devices for a security scenario), and Digital-Twin RV (robot + cloud). ROS2-Monitor-Infra extends this group by **separating data acquisition (DDS-coupled `MonitorNode`) from verdict evaluation (`VerdictRunner`, no rclpy)** at the process level, so multi-host is a first-class deployment shape, not an afterthought.

### 2. Cloud component
Only ROMoSu and Digital-Twin RV depict a cloud-side recipient (broker / DT). Neither shows a database + dashboard + offline-replay triad. ROS2-Monitor-Infra is designed so the cloud side hosts the broker, a time-series DB, dashboards, and a replay engine that re-runs the **same verdict engines** against archived JSONL traces. This is enabled by the **invariant data format (`DataRecord` JSONL)** that flows identically through DDS-fed and replay-fed paths.

### 3. Feedback to ROS
- ROSRV: message-bus enforcement (drop/rewrite).
- ROSMonitoring 2.0: service-call interception.
- Digital-Twin RV: actuation override.
- Everyone else: verdict topic only, or none.
- ROS2-Monitor-Infra: the **only** framework that targets the full ROS 2 control surface — parameter updates, service calls, message publishes, and lifecycle transitions — as feedback channels. The codebase reserves these explicitly under *Feedback · Intervention* in the architecture; the deployment diagram marks them `«planned»`.

### 4. DSL pluggability
Most works are tied to one formalism family (STL, TeSSLa, MOP, Copilot). ROSMonitoring achieves formalism agnosticism by delegating to an external Oracle. ROS2-Monitor-Infra differs by exposing a **common `DataConverter` → `VerdictService` contract** that any DSL engine can implement, with **multiple engines coexisting on the same data bus** (Section 5 of the architecture diagram: LTL / STL / CTL / Custom engines all subscribed via DSL adapters). This is the configuration-time switch documented in `config_to_deployment.md`.

### 5. UML deployment notation
No related work located uses strict UML 2.x deployment notation. Kirca et al. use explicit "device" boxes and the Digital-Twin paper labels its hosts, but neither uses `«node»` / `«artifact»` / `«deploy»` stereotypes. This is a genuine gap; ROS2-Monitor-Infra's promotion slide closes it.

### 6. Property semantics
Trace, STL, TeSSLa, MOP, RML, FRETish/Copilot, anomaly heuristics, hierarchical predicates — each tool fixes one. ROS2-Monitor-Infra leaves the verdict engine as a plugin and provides a `Verdict` schema (`property_id`, `result`, `details`) that is opaque to the bus.

## Headline differences (slide-ready bullets)

- **Edge–cloud topology** depicted as a **standard UML 2.x deployment diagram** — a notation no surveyed paper uses.
- **DSL bus**, not DSL plug — multiple verdict engines (LTL / STL / CTL / custom) coexist on the same `DataRecord` stream.
- **Full ROS 2 feedback surface** (params, services, pubs, lifecycle) — the most ambitious feedback scope among the surveyed works.
- **Offline replay parity** — the same engines run online (DDS-fed) and offline (JSONL-fed), enabled by an invariant `DataRecord` format.
- **Container-native edge deployment** with `network_mode: host` for DDS scope, paho-MQTT for cloud egress; aligns with the 2023–2025 trend (ROMoSu, Digital-Twin RV) of using MQTT as the cross-host monitor protocol.
