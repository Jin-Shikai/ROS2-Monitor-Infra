# Evaluation Master Plan

> Living document. Before each experiment starts, its *Plan* subsection is
> updated with objectives, methodology, configuration, and expected results.
> After the experiment completes, its *Results* subsection is filled with the
> actual implementation details, observations, collected metrics, and
> conclusions. Each completed experiment feeds one subsection of the thesis
> Evaluation chapter (`Thesis/chapters/evaluation.tex`).

## 1. Goals and constraints

The evaluation demonstrates the capabilities, practical value, and intended
use cases of ROS2-Monitor-Infra through five experiments of increasing
complexity. Constraints imposed on all experiments:

- **No web GUI.** Every experiment is driven purely by command-line commands
  and predefined configuration files. Topology creation, observable
  selection, and experiment configuration happen in hand-written (or
  `config_gen.py`-generated) YAML, never in the dashboard.
- Visualization tools (RViz, Gazebo GUI) may be used for illustration only;
  they are never part of the experiment control flow.
- The final experiments must demonstrate: (1) Nav2 integration, (2) multiple
  robots operating collaboratively with monitoring, and (3) LAN-distributed
  deployment where robots, Monitor, and Verdict components run on different
  physical machines and communicate via MQTT.

### Research questions

| RQ | Question | Experiments |
|----|----------|-------------|
| RQ1 | Does the monitor detect property violations correctly, and with what intrinsic latency and overhead? | E1 |
| RQ2 | Does distributing evaluation over MQTT preserve verdict correctness, and what does the transport hop cost? | E2, E5 |
| RQ3 | Can the framework observe all three ROS 2 interaction primitives (topics, services, actions)? | E2, E3 |
| RQ4 | Can an unmodified, production-grade navigation stack (Nav2) be supervised, and at what overhead? | E3, E4, E5 |
| RQ5 | Can properties spanning multiple robot traces (global predicates) be evaluated? | E4, E5 |
| RQ6 | Does the full pipeline sustain distributed operation across heterogeneous physical machines? | E5 |

## 2. Experiment overview

| # | Name | Complexity added | Status |
|---|------|------------------|--------|
| E1 | Local correctness baseline | none (reference point) | completed (2026-07-10) |
| E2 | Distribution transparency + observable breadth | MQTT split; services/actions | completed (2026-07-10) |
| E3 | Nav2 single-robot safety supervision | real navigation stack, dynamic obstacles | completed (2026-07-10) |
| E4 | Multi-robot fleet property | multiple traces, global predicate | planned |
| E5 | Heterogeneous 3-machine LAN deployment | physical distribution (Pi / PC / Mac) | planned |

## 3. Common methodology

### Entry points (all headless)

| Component | Command |
|---|---|
| Collection tier | `python3 monitor/monitor_node.py -c <yaml>` |
| Evaluation tier | `python3 monitor/node_runner.py -c <yaml>` |
| Config projection | `python3 monitor/config_gen.py <request.json> -o <dir>` |
| MQTT broker | `mosquitto -c <mosquitto.conf>` |

### Metric definitions

- **Detection latency** — wall-clock time from the collector receiving the
  triggering message (`DataRecord.timestamp`) to the verdict reaching its
  exporter (`emitted_at`, added by the evaluation-owned
  `TimestampedVerdictFileExporter`). Joined via `Verdict.input_record_ids`.
  Cross-host latency (E5) additionally requires NTP/chrony sync; the residual
  offset is reported alongside.
- **Throughput** — records per second sustained by the pipeline, per source
  and total, from record timestamps.
- **Message loss** — gaps in the per-source `record_id` sequence numbers.
- **Verdict correctness** — online verdicts compared 1:1 against an offline
  oracle: the recorded input stream re-evaluated against the same property
  definition. Reported as matched/missing/spurious transitions
  (precision/recall).
- **Resource overhead** — CPU % and RSS of monitor processes sampled from
  `/proc` (`eval/common/proc_sampler.py`); for Nav2 experiments additionally
  A/B comparison (monitor on vs. off) of the navigation stack itself.

### Shared tooling (`eval/common/`)

| File | Purpose |
|---|---|
| `eval_exporters.py` | `TimestampedVerdictFileExporter` — verdict file exporter that records wall-clock emission time (`emitted_at`) per verdict, referenced from YAML as `eval.common.eval_exporters:TimestampedVerdictFileExporter`. |
| `proc_sampler.py` | Samples CPU %, RSS of given PIDs from `/proc` to CSV. |
| `analyze_run.py` | Joins records + verdicts JSONL, runs the offline oracle, computes latency/throughput/loss/correctness metrics, writes `metrics.json`. |

Each run writes into a fresh `eval/eN/results/run_<timestamp>/` directory
containing the resolved config, raw JSONL, process samples, logs, an
environment snapshot, and computed `metrics.json`. Result directories are
git-ignored; representative metrics are recorded in this document.

---

## 4. E1 — Local correctness baseline

**Status: completed (2026-07-10)**

### Plan

- **Objective (RQ1):** establish that the monitor detects property violations
  correctly in the simplest possible setting, and measure the intrinsic
  (transport-free) detection latency and resource cost that later experiments
  are compared against.
- **Topology:** one machine (Ubuntu PC), no MQTT. Two processes:

  ```
  topic_robot.py (cmd-velocity-cycle) --/cmd_vel--> monitor_node
      [collector -> CmdVelSpeedConverter -> ThresholdVerdict -> exporters]
  ```

- **Stimulus:** `demo/common/topic_robot.py cmd-velocity-cycle` publishes
  `/cmd_vel` at 5 Hz, alternating `linear.x` between 1.85 m/s and 0.2 m/s
  every 3 s — a deterministic violate/recover square wave.
- **Property:** commanded speed limit `linear.x <= 0.5 m/s`
  (`custom.speed:CmdVelSpeedConverter` + `custom.threshold:ThresholdVerdict`,
  threshold 0.5, edge-triggered violation/recovery verdicts).
- **Configuration:** `eval/e1/monitor.yaml.in` (single topic, in-process
  converter + verdict, file exporters). Execution: `eval/e1/run.sh [duration]`.
- **Expected results:** one violation verdict at stimulus start, then one
  verdict per 3 s phase flip (~20 verdicts/60 s); offline oracle agreement
  1.0 precision/recall; detection latency in the low-millisecond range; zero
  record loss; small constant CPU/RSS footprint.
- **Metrics:** detection latency (min/mean/median/p95/max), record rate,
  record-id gaps, verdict precision/recall, monitor CPU %/RSS.
- **Thesis value:** correctness reference and intrinsic latency floor for all
  later experiments (Evaluation chapter, first experiment subsection).

### Results

**Implementation.** As planned; no deviations. Artifacts: template config
`eval/e1/monitor.yaml.in`, launcher `eval/e1/run.sh`. New shared tooling
built for this and all later experiments: `TimestampedVerdictFileExporter`
(adds `emitted_at` per verdict line; the framework itself stamps verdicts
with the *input record's* timestamp, so emission time had to be added at the
exporter level — done as an eval-owned plugin, zero framework changes),
`proc_sampler.py`, and `analyze_run.py` (offline oracle + metrics).

**Reference run** — 120 s, 2026-07-10, Ubuntu 24.04 (kernel 6.14), 16 cores,
Python 3.12.3, ROS 2 Kilted, default RMW
(`eval/e1/results/run_20260710_194001/`):

| Metric | Value |
|---|---|
| Records collected (`/cmd_vel`, 5 Hz) | 593, sustained 5.008 Hz |
| Record-id sequence gaps | 0 |
| Oracle transitions / online verdicts | 40 / 40 |
| Precision / recall | 1.0 / 1.0 |
| Detection latency mean / median | 0.36 ms / 0.36 ms |
| Detection latency p95 / max | 0.46 ms / 0.63 ms |
| Monitor CPU (steady-state mean / max sample) | 1.2 % / 24 % (startup sample) |
| Monitor RSS (max) | 73.5 MB |

A 20 s smoke run (`run_20260710_193927/`) produced consistent values
(7/7 transitions, mean latency 0.30 ms).

**Observations.** Every phase flip of the stimulus square wave produced
exactly one edge-triggered verdict whose `input_record_ids` pointed at the
first record crossing the threshold, so the online verdict stream is
byte-for-byte attributable to the recorded input. The initial violation
(stimulus starts in the violating phase at 1.85 m/s) was detected on record
`seq=1`. CPU above ~5 % appears only in the first sampling interval (rclpy
startup + DDS discovery).

**Conclusions.** (RQ1) On a single host the monitor is exact at these rates
(no loss, no missed or spurious verdicts) and the intrinsic pipeline cost is
sub-millisecond (mean 0.36 ms from collector receipt to verdict emission)
with a small constant footprint. These numbers are the baseline that E2
(MQTT hop) and E5 (LAN hops) are compared against.

---

## 5. E2 — Distribution transparency and observable breadth

**Status: completed (2026-07-10)**

### Plan

- **Objective (RQ2, RQ3):** show that splitting collection from evaluation
  over MQTT preserves verdicts (distribution transparency) and demonstrate
  topic, service, and action monitoring together. Focus is correctness;
  transport latency is reported as a secondary observation.
- **Topology:** one machine, dedicated broker on port 1884 (isolated from the
  system broker on 1883):

  ```
  topic_robot.py + reset_robot.py + action_robot.py
      --DDS--> monitor_node --MQTT(1884)--> node_runner [converters -> verdicts]
  ```

- **Correctness methodology (three independent checks):**
  1. *Distribution transparency:* the speed property is evaluated **twice**
     from the same collected records — in-process inside monitor_node and
     remotely in node_runner behind the MQTT hop. The two verdict streams
     are diffed field-by-field on `(property_id, result, input_record_ids)`
     (`eval/common/compare_verdicts.py`); they must be identical.
  2. *Oracle check:* the remote verdict stream is verified against the
     offline oracle on the monitor-side record file (as in E1).
  3. *Service/action ground truth:* `reset_robot.py` makes odd `/reset_pose`
     calls effective and even calls ineffective, so the
     `ResetPoseEffectVerdict` stream must alternate true/false starting with
     true, each verdict attributed to one service-response record and one
     `/odom` record; the Fibonacci action fixture (`eval/e2/action_robot.py`,
     order 6 every 5 s) must yield 5 feedback records and one SUCCEEDED
     status entry per goal (`eval/e2/check_extras.py`).
- **Observables:** topics `/cmd_vel`, `/odom`; service `/reset_pose`
  (introspection-based); action `/fibonacci` (feedback + status phases).
- **Configuration:** `eval/e2/monitor.yaml.in`, `eval/e2/runner.yaml.in`,
  `eval/e2/mosquitto.conf`. Execution: `eval/e2/run.sh [duration]` with
  ordered shutdown (stimuli -> monitor -> runner) so no records are in
  flight when a tier stops.
- **Expected:** identical local/remote verdict streams; oracle
  precision/recall 1.0; alternating reset verdicts; exact action record
  counts; zero loss.

### Results

**Implementation.** As planned, plus one new fixture
(`eval/e2/action_robot.py` — Fibonacci action server + periodic client; no
action fixture survived the demo cleanup) and one fixture fix discovered by
the checks themselves: `topic_robot.py` also publishes an `/odom` stream
fixed at the origin, which made ineffective resets look effective
(`distance_to_origin: 0.0` on even calls). Remapped to an unmonitored name
(`-r odom:=/speed_odom`) so `/odom` carries only `reset_robot` data — a
fixture topic collision, not a monitor defect; the correctness harness
caught it immediately.

**Reference run** — 120 s, 2026-07-10, same host/software as E1
(`eval/e2/results/run_20260710_195824/`):

| Check | Outcome |
|---|---|
| Distribution transparency (local vs. remote speed verdicts) | **identical**: 40/40 verdicts equal on property_id, result, input_record_ids |
| Remote verdicts vs. offline oracle | 40/40 matched, precision/recall 1.0 |
| Reset-pose service-effect verdicts | 39 verdicts, alternate true/false starting true, all attributed to service-response + `/odom` records |
| Fibonacci action ground truth | 23 goals -> 115 feedback records (23 x 5 exactly), 23 SUCCEEDED status entries |
| Record loss (all 4 sources, 1454 records) | 0 sequence gaps |
| Detection latency across MQTT (secondary) | mean 2.43 ms, p95 3.13 ms (vs. 0.36 ms in-process in E1 -> hop cost ~2 ms) |

Record streams observed concurrently: `/cmd_vel` 5.01 Hz, `/odom` 5.01 Hz,
`/fibonacci` feedback+status, `/reset_pose` request/response pairs — all
three ROS 2 interaction primitives in one session.

**Conclusions.** (RQ2) Moving evaluation behind an MQTT hop changed nothing
in the verdict stream — same verdicts, same order, same triggering-record
attribution — at a transport cost of ~2 ms on localhost. (RQ3) Topics,
services, and actions were all collected in one monitor session and
service records participated in a cross-primitive property (service
response correlated with subsequent odometry). The E1 vs. E2 pair
establishes the correctness invariant that E5 re-tests across physical
machines.

---

## 6. E3 — Nav2 single-robot safety supervision

**Status: completed (2026-07-10)**

### Plan

- **Objective (RQ3, RQ4):** supervise an unmodified Nav2 stack navigating a
  custom world and show that the verdicts are *correct*: every verdict is
  validated against an offline oracle (speed property) or against the
  mission's own measured outcome (goal-deadline property). Dynamically
  spawned obstacles cause the behavior changes the properties react to.
  Focus is correctness; overhead is reported briefly, robustness is out of
  scope.
- **Topology:** one machine. Gazebo (`simple_nav_world.sdf` from
  `my_nav2_worlds`) + TB3 waffle + Nav2 (`tb3_simulation_launch.py`,
  headless server; one GUI run for thesis figures) + a deterministic
  `nav2_simple_commander` mission script + `spawn_dynamic_obstacles`;
  monitor_node + node_runner split over MQTT (1884) as in E2.
- **Mission (deterministic script, logged with wall-clock timestamps):**
  goal A down the corridor with no obstacles (expected: satisfied), then
  obstacles spawned into the return path, goal B back through the obstacle
  zone (avoidance slows the robot), then a `temporary_wall` blocking the
  corridor and goal C (expected: deadline violation or abort).
- **Observables:** `/cmd_vel` (Twist or TwistStamped — verified at
  bring-up), `/odom` (rate-throttled), `/navigate_to_pose` action
  (feedback + status phases).
- **Properties:**
  - P1 commanded speed limit (threshold below Nav2's cruise speed so normal
    driving produces violation/recovery cycles; correctness = offline
    oracle on the recorded records, exact regardless of how the robot
    actually moves).
  - P2 goal deadline: each navigation goal must reach SUCCEEDED within
    `deadline_sec`; violations are detected in flight (first
    feedback/status record past the deadline) or at terminal status
    (abort/cancel). Needs a new case-study plugin (`custom/nav_goal.py`:
    `NavGoalDeadlineConverter` + `NavGoalDeadlineVerdict`), judged on
    record wall-clock timestamps. Correctness = verdict stream vs. the
    mission log's measured durations/outcomes (`eval/e3/check_goals.py`).
- **Expected:** P1 oracle precision/recall 1.0; P2 verdicts consistent with
  the mission log for every goal; goal A satisfied, goal C violated;
  violations follow the logged obstacle-spawn events.
- **Metrics:** P1 precision/recall; P2 per-goal agreement; record counts
  and loss; secondary: detection latency, monitor CPU/RSS on the Nav2 host.

### Results

**Implementation notes (deviations from plan).**
- `/cmd_vel` is `geometry_msgs/msg/TwistStamped` on Kilted Nav2;
  `CmdVelSpeedConverter` gained an optional `speed_path` constructor
  parameter (default `linear.x`, E3 uses `twist.linear.x`) — backward
  compatible, all 161 unit tests unchanged.
- New case-study plugin `custom/nav_goal.py` (`NavGoalDeadlineConverter` +
  `NavGoalDeadlineVerdict`): one verdict per `/navigate_to_pose` goal,
  violation detected in flight on the first feedback/status record past the
  deadline, or at terminal status.
- Headless bring-up requires AMCL's initial pose as a parameter
  (`eval/e3/nav2_params.yaml`, derived from stock params with
  `set_initial_pose: true` at the spawn pose); without it the global
  costmap activation times out and bringup aborts.
- Two operational hardenings in `run.sh`: purge stale simulation processes
  before launch (a leftover nav2 container registers duplicate lifecycle
  nodes and aborts the new bringup), and a bounded timeout+retry around the
  mission driver (nav2_simple_commander's activation wait can hang on a
  service-discovery race when started during bringup; no goals have been
  sent at that point, so a restart is side-effect free).
- The mission's expectation changed after calibration: the TB3 in this
  configuration cruises up to ~0.46 m/s, so goal C (blocked corridor)
  is *detoured around* the wall and succeeds quickly instead of aborting.
  Deadline set to 45 s so that A/C are satisfied and B (obstacle avoidance)
  overruns.

**Reference run** — deadline 45 s, 2026-07-10
(`eval/e3/results/run_20260710_210143/`):

| Check | Outcome |
|---|---|
| P1 speed verdicts vs. offline oracle (`twist.linear.x` > 0.2) | 10/10 matched, precision/recall 1.0 |
| P2 goal A (no obstacles, 39.7 s) | satisfied — matches mission log |
| P2 goal B (obstacles spawned into path, 62.0 s) | violated, **detected in flight** at the 45.0 s mark, 16.9 s before the goal ended |
| P2 goal C (corridor walled off, Nav2 detours, 14.4 s) | satisfied — matches mission log |
| Record loss | `/cmd_vel` 0 gaps (2145 records @ 17.8 Hz), `/navigate_to_pose` 0 gaps (11606 records @ 94.6 Hz) |
| `/odom` sequence gaps | 3274 — **by design**: RateThrottler drops from ~30 Hz to 5 Hz; gaps for throttled sources measure transformer reduction, not transport loss |
| Detection latency (speed property, across MQTT) | mean 0.53 ms |
| Monitor + runner CPU (mean/max sample) / RSS | 6.5 % / 27 % / 99 MB — Nav2 + Gazebo dominate the host |

**Observations.** The action feedback stream is by far the largest record
source (94.6 Hz — Nav2 publishes NavigateToPose feedback at its controller
rate); E4/E5 should consider throttling it. The earlier 35 s-deadline run
(`run_20260710_205812/`) is also archived: all its verdicts matched ground
truth too (A and B violations, C satisfied), demonstrating the checks are
deadline-independent.

**Conclusions.** (RQ4) An unmodified Nav2 stack was supervised end-to-end
with zero application changes: configuration names two topics and one
action, and the same converter/verdict machinery from E1/E2 applies. The
goal-deadline property demonstrated *predictive* value: the violation was
raised 17 s before the navigation action itself reported completion —
information a fleet operator could act on while the goal is still running.
(RQ3) Action monitoring carried a real property, not just record
collection.

---

## 7. E4 — Multi-robot fleet property

**Status: planned**

### Plan

- **Objective (RQ4, RQ5):** evaluate per-robot properties locally per trace
  and a fleet-level global predicate (minimum separation distance) across two
  Nav2 robots on deliberately crossing routes.
- **Topology:** one machine; `cloned_multi_tb3_simulation_launch.py`
  (namespaced `/robot1`, `/robot2`) in the custom world; one monitor_node
  observing both namespaces; one node_runner with per-robot and fleet
  verdicts.
- **New code needed:** `SeparationDistanceConverter` (fleet minimum distance
  from two `/odom` positions); goal scripts with crossing routes.
- **Expected:** independent per-robot verdict streams plus fleet verdicts
  exactly when trajectories cross below the threshold.
- **Metrics:** fleet-verdict correctness vs. offline distance oracle; record
  throughput scaling 1 -> 2 robots; global-predicate latency.

### Results

*(pending)*

---

## 8. E5 — Heterogeneous 3-machine LAN deployment

**Status: planned**

### Plan

- **Objective (RQ2, RQ6):** run the complete E4 scenario with robots,
  Monitor, and Verdict tiers on three physical machines connected over the
  LAN via MQTT, with an unchanged property set (moving tiers is pure
  configuration).
- **Role assignment:**

  | Machine | Role |
  |---|---|
  | Ubuntu PC | System under test: Gazebo + 2x Nav2 + obstacle/goal scripts (+ RViz for figures) |
  | Raspberry Pi (Ubuntu) | Monitor tier: `monitor_node` (joins the PC's DDS domain over wired LAN) + mosquitto broker |
  | MacBook (macOS) | Verdict tier: `node_runner` natively (Python + paho-mqtt; no ROS, no Docker) |

- **Data path:** robots --DDS/LAN--> monitor (Pi) --MQTT--> broker (Pi)
  --MQTT--> verdict runner (Mac) --> verdict JSONL.
- **Preconditions:** chrony/NTP sync of all three machines; ROS 2 Kilted +
  message packages on the Pi; matching `ROS_DOMAIN_ID`/RMW between PC and Pi.
- **Expected:** verdict streams equivalent to E4 for the same mission script;
  sustained multi-minute operation; optional broker-restart resilience probe.
- **Metrics:** end-to-end latency decomposed per hop; MQTT bandwidth;
  per-machine CPU/RSS (notably Pi); LAN message loss; verdict agreement with
  a single-host E4 rerun.
- **Risk / fallback:** if PC-Pi DDS discovery over the LAN proves unreliable,
  move monitor_node to the PC (broker stays on the Pi) and document the
  weaker separation as a limitation.

### Results

*(pending)*

---

## 9. Thesis mapping

| Experiment | Evaluation chapter subsection |
|---|---|
| Methodology (this section 3) | Experimental setup and metrics |
| E1 | Correctness and intrinsic overhead baseline |
| E2 | Distributed evaluation over MQTT |
| E3 | Case study: supervising Nav2 |
| E4 | Fleet-level runtime verification |
| E5 | Distributed deployment on heterogeneous hardware |
