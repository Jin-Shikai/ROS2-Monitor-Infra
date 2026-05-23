# Related-Work Survey: Deployment Depictions in ROS / ROS 2 Runtime-Verification Frameworks

> Purpose: inform the UML Deployment Diagram for **ROS2-Monitor-Infra** by examining how related work draws *where the monitor runs*.
>
> Scope: 12 papers — the four originally suggested (ROSMonitor / ROSMonitoring 2.0 / RoMuSu / Monitoring ROS2 / ros2_tracing) plus 7 additional works prioritising recent (2023–2025) publications.
>
> Honesty note: arXiv / Springer / IEEE PDFs were not directly fetchable in this session. Per-paper figure descriptions are reconstructed from abstracts, project READMEs, author preprints, and conference summaries. Statements about "UML stereotypes used / not used" reflect the strong prior across these venues; for any claim that needs to be defended on a slide, cross-check the PDF.

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

## 3. ROSMonitoring 2.0 — Ferrando & Cardoso, 2024 (preprint)

- **Citation.** Ferrando, Cardoso. *ROSMonitoring 2.0: Extending ROS Runtime Verification to Services and Ordered Topics.* arXiv:2411.14367, Nov 2024.
- **Link.** [arXiv:2411.14367](https://arxiv.org/abs/2411.14367)
- **Figure type.** Architecture diagram (v1 extended).
- **Topology.** Same Monitor↔Oracle WebSocket seam plus a *service-interception* block (Monitor sits between client and server) and an *ordering* component that timestamps and buffers messages before forwarding to the Oracle.
- **Feedback.** Stronger than v1 — RPC interception lets it block unsafe service requests.
- **DSL.** Same as v1.

## 4. ROMoSu — Stadler et al., RoSE 2023 @ ICSE

- **Citation.** Stadler et al. *ROMoSu: Flexible Runtime Monitoring Support for ROS-based Applications.* RoSE @ ICSE 2023.
- **Links.** [PDF](https://rose-workshops.github.io/files/rose2023/papers/RoSE2023_paper_3.pdf) · [IEEE](https://ieeexplore.ieee.org/document/10190384/) · [vision (2022)](https://rose-workshops.github.io/files/rose2022/papers/RoSE22_paper_4.pdf) · [code](https://github.com/MStadler-Organization/ROMoSu)
- **Figure type.** Architecture diagram (multi-component).
- **Topology.** A `Configurator / Configuration Manager` spawns `Monitor` instances dynamically per scenario; data is bridged from ROS topics onto an **MQTT broker** one-to-one. The MQTT seam is the closest indicator in the related work that they target off-board observers.
- **Feedback.** Reconfiguration only (frequencies, plans updated at runtime). No actuator-level enforcement.
- **DSL.** Scenario-driven; not multi-logic pluggable.

## 5. ros2_tracing — Bédard et al., RA-L 2022 (+ RAS 2023 follow-up)

- **Citation.** Bédard, Lütkebohle, Dagenais. *ros2_tracing: Multipurpose Low-Overhead Framework for Real-Time Tracing of ROS 2.* IEEE RA-L 7(3):6511–6518, 2022.
- **Follow-up.** Bédard, Lajoie, Beltrame, Dagenais. *Message Flow Analysis with Complex Causal Links for Distributed ROS 2 Systems.* Robotics and Autonomous Systems 161:104361, 2023.
- **Links.** [arXiv:2201.00393](https://arxiv.org/abs/2201.00393) · [code](https://github.com/ros2/ros2_tracing) · [design doc](https://github.com/ros2/ros2_tracing/blob/rolling/doc/design_ros_2.md)
- **Figure type.** Architecture diagram of instrumentation layers.
- **Topology.** Instrumented ROS 2 core + `tracetools` + LTTng-UST in-process, optional kernel LTTng, *offline* `tracetools_analysis` pipeline reading CTF trace files. Single-host in the original figure; the 2023 follow-up explicitly addresses distributed ROS 2 systems.
- **Feedback.** None (offline-first observability, not RV).
- **DSL.** N/A (not a property-language framework).

## 6. Monitoring ROS2 (FRET + Ogma + Copilot) — Perez et al., 2022

- **Citation.** Perez, Mavridou, Pressburger, Will, Martin. *Monitoring ROS2: from Requirements to Autonomous Robots.* arXiv:2209.14030, 2022 (NASA / NIA).
- **Link.** [arXiv:2209.14030](https://arxiv.org/abs/2209.14030)
- **Figure type.** Tool-chain diagram.
- **Topology.** FRET (developer machine) → Ogma codegen → Copilot C99 monitor compiled into a `ROS 2 monitor node` colocated with the application. Communication: ROS 2 DDS topics.
- **Feedback.** Verdicts published as ROS 2 topics; intervention left to user code.
- **DSL.** FRETish → temporal-logic → C99; a single chain, not pluggable across formalisms.

## 7. RTAMT / rtamt4ros — Ničković et al., 2020 / 2023 / 2025

- **Citations.**
  - Ničković, Yamaguchi. *RTAMT: Online Robustness Monitors from STL.* ATVA 2020. arXiv:2005.11827.
  - Ničković et al. *RTAMT — Runtime Robustness Monitors with Application to CPS and Robotics.* STTT 2023. Expanded preprint: arXiv:2501.18608 (2025).
- **Links.** [arXiv:2005.11827](https://arxiv.org/abs/2005.11827) · [STTT](https://link.springer.com/article/10.1007/s10009-023-00720-3) · [arXiv:2501.18608](https://arxiv.org/abs/2501.18608)
- **Figure type.** Library-layer architecture diagram.
- **Topology.** STL monitor node embedded in the ROS graph; subscribes to robot signals, emits robustness as a ROS topic. Discrete and dense-time backends.
- **Feedback.** Verdict topic only.
- **DSL.** STL-only.

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

## 10. Digital-Twin RV — Betzer et al., 2024 / IEEE 2025

- **Citation.** Betzer, Boudjadar, Frasheri, Talasila. *Digital Twin Enabled Runtime Verification for Autonomous Mobile Robots under Uncertainty.* arXiv:2412.09913, Dec 2024 (IEEE conf. proc. 10937693, 2025).
- **Links.** [arXiv:2412.09913](https://arxiv.org/abs/2412.09913) · [IEEE](https://ieeexplore.ieee.org/document/10937693/) · [Aarhus PDF](https://pure.au.dk/ws/portalfiles/portal/421738048/2412.09913v1.pdf)
- **Figure type.** Architecture diagram with explicit role-labelled hosts (closest analogue to a deployment diagram in this corpus).
- **Topology.** **Multi-host.** Two clearly separated hosts: (a) the *physical robot* running the ROS stack; (b) a **cloud-hosted Digital Twin** running TeSSLa monitors compiled from STL-like properties. Inter-host link: **MQTT**.
- **Feedback.** Yes — the DT acts as a watch-dog and **overrides actuations** when a property is about to be violated.
- **DSL.** TeSSLa-only.
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
