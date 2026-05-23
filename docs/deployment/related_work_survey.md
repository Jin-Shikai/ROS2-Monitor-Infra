# Related-Work Survey: Deployment Depictions in ROS / ROS 2 Runtime-Verification Frameworks

> Purpose: inform the UML Deployment Diagram for **ROS2-Monitor-Infra** by examining how related work draws *where the monitor runs*.
>
> Scope: 12 papers — the four originally suggested (ROSMonitor / ROSMonitoring 2.0 / RoMuSu / Monitoring ROS2 / ros2_tracing) plus 7 additional works prioritising recent (2023–2025) publications.
>
> **Verification status (2026-05-23 revision).** The PDFs for entries 1–8 (ROSMonitoring, ROSMonitoring 2.0, ROMoSu, ros2_tracing, Monitoring ROS2, RTAMT, Digital-Twin RV) have been read end-to-end; their entries below have been corrected against the actual papers and cross-referenced with `paper_summaries.md`. Entries 9, 11, 12 (Caldas et al., RMoM, Kirca et al.) are still based on abstracts / public records — flagged inline. ROSRV (entry 1) is also still based on secondary sources.

---

## 1. ROSRV — Huang et al., RV 2014

- **Citation.** Huang, Erdogan, Zhang, Moore, Luo, Sundaresan, Roșu. *ROSRV: Runtime Verification for Robots.* RV 2014. Springer LNCS 8734, 247–254.
- **Links.** [Springer](https://link.springer.com/chapter/10.1007/978-3-319-11164-3_20) · [FSL PDF](https://fsl.cs.illinois.edu/publications/huang-erdogan-zhang-moore-luo-sundaresan-rosu-2014-rvtool.pdf) · [code](https://github.com/cansuerdogan/ROSRV)
- **Figure type.** Architecture diagram (not UML deployment notation).
- **Topology.** Single host. The `RVMaster` process sits *between* ROS nodes and the firewall-protected ROS Master; monitors are generated from MOP/RV-Monitor specifications and embedded inside `RVMaster`. Communication: XML-RPC + ROS TCP/UDP.
- **Feedback.** Yes — `RVMaster` may drop, rewrite, or block commands on violation (built-in enforcement).
- **DSL.** Single formalism family (MOP / parametric trace specs).

## 2. ROSMonitoring — Ferrando et al., TAROS 2020

- **Citation.** Ferrando, Cardoso, Fisher, Ancona, Franceschini, Mascardi. *ROSMonitoring: A Runtime Verification Framework for ROS.* TAROS 2020. Springer LNAI 12228, 387–399.
- **Links.** [Springer](https://link.springer.com/chapter/10.1007/978-3-030-63486-5_40) · [preprint](https://unige.iris.cineca.it/retrieve/e268c4cd-59c8-a6b7-e053-3a05fe0adea1/ROSMonitoring_ICRA2020.pdf) · [code](https://github.com/autonomy-and-verification-uol/ROSMonitoring)
- **Figure type.** Architecture diagram.
- **Topology.** A `Monitor` node is inserted into the ROS graph by topic renaming; an external `Oracle` (Prolog/RML web-server) evaluates traces. Effectively single-host in the figure, but the **WebSocket+JSON Monitor↔Oracle** seam allows the oracle off-board in principle.
- **Feedback.** Limited — the Monitor can suppress violating messages on the renamed topics.
- **DSL.** Formalism-agnostic via Oracle (default RML).

## 3. ROSMonitoring 2.0 — Ghaffari Saadat et al., FMAS 2024

- **Citation (corrected against PDF).** Ghaffari Saadat, Ferrando, Dennis, Fisher. *ROSMonitoring 2.0: Extending ROS Runtime Verification to Services and Ordered Topics.* FMAS 2024, EPTCS 411, pp. 38–55. doi:10.4204/EPTCS.411.3.
- **Link.** [EPTCS 411.3](https://doi.org/10.4204/EPTCS.411.3)
- **Figure type.** Architecture diagram (v1 extended); Fig. 3 sequence diagram for service interception; Fig. 4 case-study graph with extra monitoring topics.
- **Topology.** Same Monitor↔Oracle WebSocket seam plus *service interception* (Monitor as server-to-client and client-to-server) and a *publication-time reordering* component with per-topic timestamp buffers (Lemma 1 + Theorem 1 of correctness, plus an explicit deadlock-risk analysis).
- **Feedback.** Stronger than v1 — RPC interception **blocks unsafe service requests** and substitutes an error response to the client.
- **DSL.** Same formalism-agnostic Oracle. Examples are written in **Past MTL via Reelay**; **three-valued verdicts** (⊤, ⊥, ?, with ?⊤ / ?⊥).
- **Implementation.** ROS 1 Noetic full feature set; **ROS 2 port is partial** (service monitoring only, no reordering). [code](https://github.com/autonomy-and-verification-uol/ROSMonitoring) (`ros2` branch).

## 4. ROMoSu — Stadler & Vierhauser, RoSE 2023 @ ICSE

- **Citation (corrected against PDF).** Stadler, Vierhauser (LIT SCS Lab, JKU Linz). *ROMoSu: Flexible Runtime Monitoring Support for ROS-based Applications.* RoSE @ ICSE 2023.
- **Links.** [PDF](https://rose-workshops.github.io/files/rose2023/papers/RoSE2023_paper_3.pdf) · [IEEE](https://ieeexplore.ieee.org/document/10190384/) · [vision (2022)](https://rose-workshops.github.io/files/rose2022/papers/RoSE22_paper_4.pdf)
- **Figure type.** Multi-component architecture diagram with four parts (Framework Core, Admin UI, Dashboard, external Services).
- **Topology.** **Non-invasive instrumentation via `roslibpy` / `rosbridge`** (no source modification, no topic remap). Data are republished onto a **Mosquitto MQTT broker** in JSON. External services attached over MQTT: **InfluxDB** for persistence and **Esper CEP** for constraint checking.
- **Feedback.** **Purely passive.** Reconfiguration of frequencies / topics happens via the Admin UI; no closed-loop write-back into ROS.
- **DSL.** **No native property DSL.** Constraint checks delegate to **Esper EPL**; supports static value (S) and temporal/windowed (T) checks (e.g. 10 s average).
- **Implementation.** Angular + Django + SQLite + InfluxDB + Mosquitto + roslibpy + Esper (Java). InfluxDB in Docker. Tested with **ROS 1** (TurtleBot 3 + Gazebo); no ROS 2 claim. Authors commit to open-sourcing; no URL in the preprint. Reported event-volume reduction up to **95.48 %** vs brute-force monitoring; average EPT 0.27 ms.

## 5. ros2_tracing — Bédard, Lütkebohle, Dagenais, RA-L 2022 (+ RAS 2023 follow-up)

- **Citation.** Bédard, Lütkebohle, Dagenais. *ros2_tracing: Multipurpose Low-Overhead Framework for Real-Time Tracing of ROS 2.* IEEE RA-L 7(3):6511–6518, 2022.
- **Follow-up.** Bédard, Lajoie, Beltrame, Dagenais. *Message Flow Analysis with Complex Causal Links for Distributed ROS 2 Systems.* Robotics and Autonomous Systems 161:104361, 2023.
- **Links.** [arXiv:2201.00393](https://arxiv.org/abs/2201.00393) · [code](https://github.com/ros2/ros2_tracing) · [design doc](https://github.com/ros2/ros2_tracing/blob/rolling/doc/design_ros_2.md)
- **Figure type.** Architecture diagram of instrumentation layers.
- **Topology.** Instrumented ROS 2 core (**rclcpp / rcl / rmw — no rclpy**) + `tracetools` indirection lib + LTTng-UST in-process (~158 ns per userspace tracepoint), optional kernel LTTng, *offline* `tracetools_analysis` Python pipeline reading **CTF** trace files. Single-host in the original figure; the 2023 follow-up addresses distributed ROS 2 systems.
- **Feedback.** None (offline-first observability, not RV). DDS middleware **not** instrumented.
- **DSL.** N/A (instrumentation only; user analysis scripts live on top of `tracetools_analysis`).
- **Performance.** **Mean end-to-end latency overhead 0.0033 ms** (60-min `performance_test` with all tracepoints enabled); 50 % of data between 0.0010 and 0.0056 ms.

## 6. Monitoring ROS2 (FRET + Ogma + Copilot) — Perez et al., 2022

- **Citation (corrected against PDF).** Perez, Mavridou, Pressburger, Will, Martin (KBR / NASA Ames + VCU). *Monitoring ROS2: from Requirements to Autonomous Robots.* FMAS+AVoCS 2022, EPTCS 371, pp. 208–216. doi:10.4204/EPTCS.371.15.
- **Link.** [EPTCS 371.15](https://doi.org/10.4204/EPTCS.371.15)
- **Figure type.** Tool-chain diagram.
- **Topology.** FRET (developer machine) → Ogma codegen → **Copilot C99 monitor** compiled into a *monitoring node* + *logging node* ROS 2 package, colocated with the application. Communication: ROS 2 DDS topics.
- **Feedback.** **No filtering / enforcement** — explicitly: "In contrast to ROSMonitoring, we do not provide message filtering capabilities." Violations published as **empty messages** on `copilot/handler<propname>`.
- **DSL.** **FRETish** (structured NL) → past-time MTL → Copilot stream spec → C99; a single chain, not pluggable across formalisms.
- **Implementation maturity.** Generated C99 + C++ wrapper. Branch of [github.com/nasa/ogma](https://github.com/nasa/ogma). **No quantitative evaluation** in the paper (UAM example is motivating only).

## 7. RTAMT / rtamt4ros — Yamaguchi, Hoxha, Ničković — STTT 2025 (extends ATVA 2020)

- **Citations (corrected against PDF).**
  - Ničković, Yamaguchi. *RTAMT: Online Robustness Monitors from STL.* ATVA 2020. arXiv:2005.11827.
  - Yamaguchi, Hoxha, Ničković. *RTAMT — Runtime Robustness Monitors with Application to CPS and Robotics.* STTT accepted; arXiv:2501.18608v1.
- **Links.** [arXiv:2005.11827](https://arxiv.org/abs/2005.11827) · [arXiv:2501.18608](https://arxiv.org/abs/2501.18608)
- **Figure type.** Library-layer architecture diagram (Fig. 5 class diagram with `StlAst` / visitors / `TimeInterpreter`).
- **Topology.** **`rtamt4ros`**: a single Python monitor ROS node using `rospy` **introspection / reflection** to dynamically create subscribers + publishers per variable. Topic mapping via `@topic(...)` annotations in a `.stl` file. Python + **C++ backend via Boost.Python (≈10× faster)**.
- **Feedback.** Robustness number published on a ROS topic (e.g. `rtamt/rob`). Used externally for **falsification testing** in Simulink, but no built-in enforcement.
- **DSL.** **STL** (bfSTL, pSTL, **Interface-Aware STL with output robustness μ and input vacuity ν**). Online uses **pastification** automatically; discrete + dense-time supported.

## 8. TeSSLa-ROS-Bridge — Kallwies, Leucker, Schmitz et al., ICTAC 2023

- **Citation.** Kallwies, Leucker, Schmitz et al. *TeSSLa-ROS-Bridge — Runtime Verification of Robotic Systems.* ICTAC 2023. Springer LNCS.
- **Links.** [Springer](https://link.springer.com/chapter/10.1007/978-3-031-47963-2_23) · [Uni Lübeck](https://www.isp.uni-luebeck.de/research/publications/tessla-ros-bridge-runtime-verification-robotic-systems) · [tool blog](https://www.tessla.io/blog/rosBridge/)
- **Figure type.** Architecture diagram.
- **Topology.** TeSSLa spec → generated monitor → `Bridge` ROS node subscribing to topics declared by spec annotations. Outputs verdicts / derived streams back as ROS topics.
- **Feedback.** Verdict topic only.
- **DSL.** TeSSLa-only.

## 9. Runtime Verification + Field-Based Testing — Caldas et al., 2024

- **Citation.** Caldas, Piñera García, Schiopu, Pelliccione, Rodrigues, Berger. *Runtime Verification and Field-based Testing for ROS-based Robotic Systems.* arXiv:2404.11498, 2024 (under review for IEEE TSE-class venue).
- **Links.** [arXiv:2404.11498](https://arxiv.org/abs/2404.11498) · [Chalmers PDF](https://research.chalmers.se/publication/542744/file/542744_Fulltext.pdf)
- **Figure type.** Conceptual architecture figures of an RV pipeline; methodological survey rather than a single tool.
- **Topology.** Discusses both onboard and offboard monitoring; field testing emphasises onboard.
- **Feedback.** Treated as an open dimension.
- **DSL.** Survey.

## 10. Digital-Twin RV — Betzer, Boudjadar, Frasheri, Talasila — arXiv 2024

- **Citation (corrected against PDF).** Betzer, Boudjadar, Frasheri, Talasila (Aarhus University). *Digital Twin Enabled Runtime Verification for Autonomous Mobile Robots under Uncertainty.* arXiv:2412.09913v1, Dec 2024.
- **Links.** [arXiv:2412.09913](https://arxiv.org/abs/2412.09913)
- **Figure type.** Architecture diagram (Fig. 1) plus a workflow figure (Fig. 2: Sense → Analyze → MQTT → DT monitors → Validate → Execute / re-Sense).
- **Topology.** **Multi-host.** Physical Twin = Turtlebot 3 Burger + RPi + hector SLAM; Digital Twin (cloud) hosts TeSSLa-synthesized monitors via the **TeSSLa Telegraf Connector** (TeSSLa → Rust over UDP into Telegraf). Inter-host link: **MQTT** (`test.mosquitto.org:1883` in the demo). InfluxDB for persistence / replay.
- **Feedback.** Yes — the DT acts as a watch-dog: **blocks unapproved actuations** (robot re-senses) and **overrides** by sending an adjusted speed. Reported **41 % MSE reduction** between actual and expected speed on bumpy-terrain T3B experiment.
- **DSL.** **TeSSLa-only.** Three properties: P1 braking distance, P2 tolerance, P3 Lidar validation (only P2 evaluated end-to-end).
- **Why relevant.** This paper's topology is the closest match to ROS2-Monitor-Infra's final-form deployment. It still does not use UML deployment notation.

## 11. RMoM — Hu et al., IEEE TR 2019

- **Citation.** Hu, Dong, Yang, Shi, Zhou. *Runtime Verification on Hierarchical Properties of ROS-Based Robot Swarms.* IEEE Trans. on Reliability, 2019.
- **Link.** [IEEE](https://ieeexplore.ieee.org/abstract/document/8759088)
- **Figure type.** Multi-layer architecture diagram.
- **Topology.** Multiple robots in a swarm plus a separate verification device; monitors at resource / communication / robot / swarm layers.
- **Feedback.** Verdicts per layer; intervention not central.
- **DSL.** Built on ROSMonitoring formalisms.

## 12. Anomaly-Detection RV — Kirca et al., MDPI Machines 2023

- **Citation.** Kirca et al. *Runtime Verification for Anomaly Detection of Robotic Systems Security.* Machines (MDPI) 11(2):166, 2023.
- **Link.** [MDPI](https://www.mdpi.com/2075-1702/11/2/166)
- **Figure type.** Three-entity diagram with explicit "device" boxes (verification device / attacker device / robotic platform). The closest in the corpus to a deployment-style figure, though no UML stereotypes.
- **Topology.** Multi-host (3 devices), ROS-network communication.
- **Feedback.** Detection only.
- **DSL.** Built on ROSMonitoring.

---

## Foundational / adjacent works cited above

- **MOP / RV-Monitor.** Chen & Roșu, RV 2003; Luo, Zhang, Lee, Jin, Meredith, Șerbănuță, Roșu. *RV-Monitor.* RV 2014. [Springer](https://link.springer.com/chapter/10.1007/978-3-319-11164-3_24)
- **DejaVu.** Havelund, Peled, Ulus. *DejaVu: A Monitoring Tool for First-Order Temporal Logic.* IEEE 2018. [IEEE](https://ieeexplore.ieee.org/document/8429480)
- **Copilot.** Stream DSL → C99 monitors. [code](https://github.com/Copilot-Language/copilot/)
- **AS2FM.** Henkel et al. *AS2FM: Enabling Statistical Model Checking of ROS 2 Systems for Robust Autonomy.* arXiv:2508.18820, 2025. (Model checking, not RV — included for currency.)

## Could not locate

- A paper literally titled "ROSMonitor 2.0" — the actual extension is **ROSMonitoring 2.0** (arXiv:2411.14367), treated as such in this survey.

---

## Cross-Cutting Patterns

1. **Default = single-host, ROS-graph-embedded monitor node.** ROSRV, ROSMonitoring (v1 and v2), RTAMT/rtamt4ros, TeSSLa-ROS-Bridge, and the FRET/Ogma/Copilot chain all colocate the monitor with the application. Diagrams are flat: one bounding box for the robot, several internal sub-boxes for nodes, arrows = ROS topics.
2. **Multi-host appears specifically when external observers are needed.** RMoM, Kirca et al., the Digital-Twin RV paper, and ROMoSu (via MQTT). When a second host is drawn, it is *always* labelled by role — "Verification device", "Oracle host", "Cloud DT" — and the link is *either* ROS-over-network *or* MQTT.
3. **MQTT is the de facto cross-host protocol in 2023–2025 ROS RV work.** ROMoSu and the Digital-Twin paper both use MQTT. DDS-over-WAN remains rare in *monitoring* deployments.
4. **Feedback channels back to ROS are still rare and shallow.** Only ROSRV (drop/rewrite), ROSMonitoring 2.0 (service interception), and the Digital-Twin paper (actuation override) close the loop. STL/STL-robustness tools emit verdict topics but leave intervention to user code. **Param updates, ROS 2 service calls, and lifecycle transitions as feedback are essentially unrepresented in the literature.**
5. **No paper located uses strict UML deployment notation** (`«node»` / `«artifact»` / `«device»`, dashed `«deploy»` arrows). All diagrams are ad-hoc component / box-and-arrow. This is a real gap that ROS2-Monitor-Infra can claim.
6. **DSL pluggability is partial at best.** ROSMonitoring is formalism-agnostic via an external Oracle (default RML/Prolog). RTAMT is STL-only; TeSSLa is TeSSLa-only; Copilot is Copilot-only. **No framework located simultaneously supports LTL + STL + CTL + custom verdict engines exposed via a single export bus.**

## Empty Cell in the Matrix — What ROS2-Monitor-Infra Can Claim

Combining the dimensions above, ROS2-Monitor-Infra occupies an empty cell:

- **Plugin-based RV framework for ROS 2** that lets users mix-and-match LTL / STL / CTL / custom verdict engines under one bus (others are tied to a single formalism).
- **Edge–cloud loop drawn as a UML deployment diagram** (others use ad-hoc architecture diagrams; Digital-Twin RV is closest but does not use UML notation).
- **Native ROS 2 feedback surface** — parameters, services, lifecycle transitions, message publishes — rather than only "drop/rewrite messages" (ROSRV) or "override actuation" (Digital-Twin RV). *(Status in code: planned; design slot is reserved in the diagram.)*
- **Clean DDS-in + MQTT-out separation across an edge-container boundary**, with offline replay parity. ros2_tracing handles offline analysis but not online RV; ROSMonitoring supports both but only inside ROS.
