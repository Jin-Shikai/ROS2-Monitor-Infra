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
| E4 | Multi-robot fleet property | multiple traces, global predicate | completed (2026-07-12) |
| E5 | Heterogeneous 3-machine LAN deployment | physical distribution (Pi / PC / Mac) | completed (2026-07-14) |

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
  goal A crosses the lower opening of the right partition as the unobstructed
  baseline. Before goal B, one barrier bridges that complete lower opening,
  forcing the return route through the upper opening. The lower barrier is
  retained and the upper opening is closed before goal C, disconnecting the
  east and west halves and exercising Nav2's no-route behavior.
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
  the mission log for every goal. Independent Gazebo checks require A to
  cross the lower opening, B to cross the upper opening, and C not to cross
  the fully closed partition. Goal polarity is derived from measured outcome
  and duration rather than assumed in advance.
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
- Headless bring-up requires AMCL's initial pose at the Gazebo spawn
  `(-2.0, -0.5)`. It is preset in `eval/e3/nav2_params.yaml` and explicitly
  assigned to BasicNavigator before the mission; simulator ground truth now
  independently checks the spawn and every successful endpoint.
- Operational hardening in `run.sh`: a dedicated cleanup script removes
  stale monitor/Nav2/Gazebo/RViz/obstacle processes and verifies MQTT port
  1884 before and after every run. The mission no longer calls
  `waitUntilNav2Active()` (whose lifecycle `get_state` response can be lost
  despite an active stack); a bounded check waits for the actual prerequisites,
  an AMCL pose and the NavigateToPose action. Retry is allowed only before a
  goal could have been sent.
- The former scattered `three_boxes` and center `temporary_wall` did not
  alter route connectivity: A, B, and C all crossed the same lower opening.
  They were replaced by two 0.5 x 1.2 x 1.0 m barriers that bridge the full
  lower and upper gaps in the right partition. `check_routes.py` derives the
  crossing coordinates from Gazebo ground truth and makes this topology an
  explicit pass/fail condition.

**Reference run** — deadline 35 s, 2026-07-12
(`eval/e3/results/run_20260712_221012/`):

| Check | Outcome |
|---|---|
| P1 speed verdicts vs. offline oracle (`twist.linear.x` > 0.2) | 10/10 matched, precision/recall 1.0 |
| P2 goal A (clear lower route, 63.4 s) | deadline violation, detected in flight — matches mission log |
| P2 goal B (lower opening closed, 68.5 s) | rerouted through upper opening; deadline violation detected in flight — matches mission log |
| P2 goal C (both openings closed, 30.1 s) | Nav2 `FAILED`; terminal violation — matches mission log |
| Route ground truth at x=1.4 | A lower y=-1.302; B upper y=+1.009; C no crossing; all topology checks pass |
| Physical endpoint truth | initial error 0; A 0.084 m; B 0.071 m (0.5 m tolerance) |
| Record loss | `/cmd_vel` 0 gaps (3139 records @ 19.1 Hz), `/navigate_to_pose` 0 gaps (16194 records @ 98.4 Hz) |
| `/odom` sequence gaps | 4324 — **by design**: RateThrottler drops from ~30 Hz to 5 Hz; gaps for throttled sources measure transformer reduction, not transport loss |
| Detection latency (speed property, across MQTT) | mean 0.63 ms |
| Monitor + runner CPU (mean/max sample) / RSS | 7.3 % / 34.0 % / 97.0 MB — Nav2 + Gazebo dominate the host |

**Observations.** The action feedback stream is by far the largest record
source (~98 Hz — Nav2 publishes NavigateToPose feedback at its controller
rate). Closing a whole topological opening, rather than placing obstacles
near a nominal path, is what makes route choice deterministic. With both
openings closed, Nav2 reports failure before the 35 s deadline; P2 still
correctly emits a violation because terminal success is required.

**Conclusions.** (RQ4) An unmodified Nav2 stack was supervised end-to-end
with zero application changes: configuration names two topics and one
action, and the same converter/verdict machinery from E1/E2 applies. The
goal-deadline property demonstrated *predictive* value: the violation was
raised about 33.5 s before goal B reported completion; it also correctly
classified goal C's early terminal failure without waiting for the deadline.
Both are information a fleet operator could act on while supervising goals.
(RQ3) Action monitoring carried a real property, not just record
collection.

---

## 7. E4 — Multi-robot fleet property

**Status: completed (2026-07-12)**

### Plan

- **Objective (RQ4, RQ5):** evaluate per-robot properties independently per
  trace and a fleet-level global predicate (minimum separation distance)
  that fuses observations from two Nav2 robots on deliberately crossing
  routes. Focus: correctness of the fleet predicate against an offline
  distance oracle.
- **Topology:** one machine; two namespaced Nav2 stacks (`/robot1`,
  `/robot2`, shared `params_file`, autostart) in the custom corridor world,
  brought up by `eval/e4/fleet_launch.py` — a reduction of the stock
  `cloned_multi_tb3_simulation_launch.py` chain with exactly one `/clock`
  bridge (the stock per-robot bridges each publish `/clock`; two publishers
  make subscribers observe sim time jumping backwards, clearing TF buffers
  and aborting goals at random — found during the smoke test). One
  monitor_node observing both namespaces; one node_runner (MQTT via broker
  on 1884) hosting two per-robot converter chains plus the fleet chain.
- **Mission (crossing patrol):** robot1 spawns at (-2.0, -0.5, 0), robot2 at
  (2.5, 0.0, pi) — the two ends of the E3 corridor route. Leg 1: the robots
  swap positions simultaneously, forcing a head-on pass inside the central
  room (x in [-1.4, 1.4], ~2.8 m wide); leg 2: they swap back, producing a
  second pass. Each pass must drive fleet separation below the threshold and
  back above it: expected verdict pattern per leg is violation -> recovery.
  AMCL initial poses are set per robot from the mission script
  (`BasicNavigator(namespace=...)` + `setInitialPose`) because the shared
  params file cannot carry two different poses; stock Kilted nav2 params
  otherwise.
- **Properties:**
  - P1 per robot (x2): commanded speed limit on `/robotN/cmd_vel`
    (`CmdVelSpeedConverter`, `speed_path: twist.linear.x`, threshold
    0.3 m/s; TB3 cruises ~0.46 m/s, so each robot produces its own
    violation/recovery stream) — property_ids `speed_robot1`,
    `speed_robot2`.
  - P2 fleet: minimum separation `dist(p1, p2) >= 1.0 m` from the two
    `/robotN/odom` position streams — NEW `SeparationDistanceConverter`
    (pairs latest positions across namespaces) + `SeparationDistanceVerdict`
    (edge-triggered on the threshold, violation when below), in
    `custom/separation.py` with unit tests.
- **Observed channels:** `/robotN/cmd_vel` (TwistStamped, full),
  `/robotN/odom` (FieldExtractor to pose x/y + linear.x, RateThrottler
  5 Hz). No action monitoring in E4 (covered by E3; NavigateToPose feedback
  at ~95 Hz per robot would dominate the record volume).
- **Correctness checks:**
  - per-robot speed verdicts vs. the existing offline oracle
    (`analyze_run.py`, one pass per robot) — also demonstrates namespace
    isolation: robot1 records never contribute to robot2 verdicts;
  - fleet verdicts vs. a NEW offline distance oracle
    (`eval/e4/check_separation.py`): replay recorded odom records in
    collection order, recompute pairwise distance, derive the expected
    edge-triggered transition sequence, and match it 1:1 against the verdict
    stream (direction, attribution via `input_record_ids`, timestamps);
  - mission ground truth: >= 1 violation episode per leg while both robots
    are between their goals;
  - simulator ground truth: violation episodes must correspond 1:1 with
    sub-threshold episodes of the robots' physical world poses
    (`gt_logger.py` streaming Gazebo `dynamic_pose/info`, `check_gt.py`) —
    added after discovering that AMCL estimates degrade during robot-robot
    contact.
- **Metrics:** fleet-verdict precision/recall vs. oracle; per-robot record
  rates and seq-gap loss; detection latency (`emitted_at` vs. input record
  timestamp); monitor/runner CPU+RSS vs. E3 (throughput scaling 1 -> 2
  robots).
- **Robot model (added during bring-up):** two stock TB3 waffles are
  *mutually invisible* to each other's lidar — the scan plane (z ~0.16 m)
  passes above the other robot's body (top ~0.10 m). Verified by probes:
  walls/boxes (which cross the plane) return echoes, a sibling robot does
  not, and both robot-robot and robot-wall physical collision do work. The
  E4 robots therefore use `gz_waffle_visible.sdf.xacro` — stock model plus
  a primitive cylinder visual spanning z 0.09–0.31 m (sensing only,
  collision geometry unchanged) so Nav2's costmaps can perceive fleet
  members. Without it the robots physically collide during the crossings,
  wheel slip corrupts odometry, and AMCL error grows to ~0.4 m.
- **Risks:** two robots meeting exactly inside a 1.2–1.4 m wall gap could
  deadlock — routes meet in the central room instead; if Nav2 mutual
  avoidance stalls a leg, the mission's `--cancel-after` bound guarantees
  termination and the oracle comparison remains valid (correctness is
  judged on whatever trajectory actually occurred).

### Results

**Implementation notes (deviations from plan).**
- New plugin `custom/separation.py` (`SeparationDistanceConverter` +
  `SeparationDistanceVerdict`, manifests, 7 unit tests — suite now 168):
  pairs the latest map-frame position of each robot and emits the pairwise
  distance; the verdict is edge-triggered on the `min_distance` threshold.
- The separation input is `/robotN/amcl_pose`, not `/robotN/odom`: each
  robot's odom frame is anchored at its own spawn pose, so odom positions
  do not share a frame. The converter gained a `topic_suffix` parameter.
- `eval/e4/fleet_launch.py` replaces the stock
  `cloned_multi_tb3_simulation_launch.py`: the stock chain starts one
  ros_gz clock bridge **per robot**, and two `/clock` publishers make
  subscribers observe sim time jumping backwards (TF buffers clear, goals
  abort randomly, confirmed by `ros2 topic info /clock`). The E4 launch
  starts a single clock bridge plus per-robot bridges without the clock
  entry (`tb3_bridge_noclock.yaml`).
- AMCL initial poses are published per robot on `/robotN/initialpose` by
  `run.sh` between localization and navigation activation (the shared
  params file cannot carry two poses; navigation costmap activation blocks
  on the map->base_link transform, so the poses must arrive during
  bringup). `eval/e4/nav2_params.yaml` = stock params with
  `update_min_d/a` lowered to 0.1 m / 0.15 rad for a denser AMCL stream.
- **Mutual lidar blindness (found via probes, fixed in the robot model):**
  two stock TB3 waffles cannot see each other — the lidar plane (~0.16 m)
  passes above the sibling's body (~0.10 m). In the first reference run
  (`run_20260712_180144`, archived) the robots physically collided during
  both crossings: Gazebo ground truth shows contact (min 0.146 m,
  interpenetration during the scuffle), wheel slip corrupted odometry by
  meters, and AMCL error grew to ~0.4 m — one physical sub-threshold
  episode went undetected because AMCL *over*-estimated the distance
  (`run_20260712_182351`, archived, `gt.json ok: false`). Fix:
  `gz_waffle_visible.sdf.xacro` adds a primitive cylinder visual spanning
  the scan plane (sensing only; collisions unchanged). Probes that
  established the facts: single-clock fix verification, lidar
  visibility teleport test, wall ram (robot stops at wall face while wheel
  odom drifts 1.5 m), robot-robot ram (contact at 0.254 m center
  distance), primitive-vs-mesh visual visibility test.
- Simulator ground truth added to the harness: `gt_logger.py` streams
  `/world/default/dynamic_pose/info` to CSV (10 Hz); `check_gt.py`
  cross-validates verdict violation episodes against physical
  sub-threshold episodes.

**Reference run** — SEP_MIN 1.0 m, SPEED_MAX 0.3 m/s, 2026-07-12
(`eval/e4/results/run_20260712_183145/`):

| Check | Outcome |
|---|---|
| Mission | 4/4 goals SUCCEEDED (leg 1: 18.0 / 41.2 s; leg 2: 23.7 / 16.5 s — robot2's 41.2 s shows real mutual avoidance) |
| P2 fleet separation vs. offline distance oracle | 10/10 transitions matched exactly (polarity, recomputed distance, `input_record_ids`, timestamps) |
| P2 vs. simulator ground truth | both physical sub-1.0 m episodes (10.4 s min 0.384 m; 4.1 s min 0.49 m) covered by verdict episodes, no unmatched episode on either side |
| AMCL vs. physical minimum separation | 0.408 m vs. 0.384 m — estimates track truth when no contact occurs |
| P1a speed robot1 vs. oracle | 6/6, precision/recall 1.0 |
| P1b speed robot2 vs. oracle | 8/8, precision/recall 1.0 (namespace isolation: each stream matches its own robot's records exactly) |
| Per-leg mission expectation | >= 1 separation violation in each leg |
| Record loss | 0 gaps on all four unthrottled channels (874 + 1193 cmd_vel, 87 + 123 amcl_pose records); odom gaps = RateThrottler by design |
| Detection latency | separation mean 0.52 ms; speed 0.67 / 0.72 ms (across MQTT) |
| Monitor CPU / RSS | 3.3 % mean (max 24 %), 91 MB — 3281 records total |

**Observations.** The AMCL-based separation values are asynchronously
sampled (latest-pose pairing), so instantaneous distances can be off by
roughly v * dt between the two robots' updates; the ground-truth
comparison bounds this error in practice (0.41 vs. 0.38 m at minimum).
The archived blind-robot runs are kept deliberately: they document that
the fleet property detected genuine near-collisions (physical contact)
that the navigation stack was structurally unable to perceive — and also
where the estimator-dependent limit of such detection lies.

**Conclusions.** (RQ5) A global predicate spanning two robot traces was
evaluated by the same converter/verdict machinery used for per-robot
properties — fusing streams is a matter of linking two sources into one
converter in the runtime configuration. Fleet verdicts matched the
offline oracle exactly and, independently, the simulator's physical
ground truth. (RQ4) Two full Nav2 stacks were supervised concurrently by
one monitor at ~3 % mean CPU. The experiment also demonstrated the
diagnostic value of runtime monitoring during its own bring-up: the
separation property exposed both a simulator integration bug (duplicate
`/clock` bridges) and a genuine multi-robot sensing blind spot (mutual
lidar invisibility) before any thesis claim depended on them.

---

## 8. E5 — Heterogeneous 3-machine LAN deployment

**Status: completed (2026-07-14)**

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

### Preparation (completed 2026-07-13)

All preconditions verified with a minimal three-machine probe (PC
`topic_robot.py cmd-velocity-cycle` --DDS--> Pi monitor_node --MQTT
1884--> Mac node_runner): 147 records collected on the Pi, 10/10 verdicts
identical between the Pi-local and Mac-remote evaluations with matching
`input_record_ids` attribution. Probe artifacts live in `~/e5_probe/` on
the Pi and Mac (not part of the E5 harness).

- **Machines** (one wired LAN, 192.168.2.0/24): PC 192.168.2.50 (Ubuntu
  24.04, ROS 2 Kilted); Raspberry Pi 192.168.2.18 on eth0 (Ubuntu 24.04.3
  aarch64, 8 GB — also has wlan0 at .19, prefer eth0); MacBook
  192.168.2.100 (macOS 15.7.3, arm64, no ROS).
- **Installed for E5:** Pi — `ros-kilted-ros-base`, `ros-kilted-nav2-msgs`,
  mosquitto 2.0.18, python3-pip, paho-mqtt 2.1.0 (user site); Mac —
  Homebrew Python 3.12 with paho-mqtt 2.1.0 + PyYAML (`--user
  --break-system-packages`). Repo rsynced to `~/ROS2-Monitor-Infra` on
  both (exclude `.git .venv results/ __pycache__ Thesis output`).
- **DDS PC<->Pi verified** both with `ros2 topic echo` and with
  monitor_node collecting `/cmd_vel` at 5 Hz — default `ROS_DOMAIN_ID` (0)
  and default `rmw_fastrtps_cpp` on both; the plan's fallback is not
  needed.
- **Clock sync:** systemd-timesyncd on PC (-1.6 ms vs. NTP) and Pi
  (+0.5 ms); macOS timed (+3.4 ms). Observed cross-host
  `emitted_at - timestamp` in the probe ranged +18 ms to **-22 ms** —
  NTP-level residual offset dominates single-hop latency, so E5 must
  report the offset alongside (consider chrony peering PC/Pi/Mac against
  one local server for tighter bounds).
- **Gotchas found during preparation:**
  1. *macOS Local Network privacy (macOS 15):* a `nohup`-detached
     node_runner whose SSH session has exited is **silently denied LAN
     TCP** — paho retries forever with no socket and no error. Run the
     Mac tier as a child of a live SSH session (the E5 orchestrator must
     hold the session open for the run duration).
  2. *Pi environment:* `PYTHONPATH` must be appended, not overwritten
     (`PYTHONPATH="$PWD:$PWD/monitor:$PYTHONPATH"`), otherwise sourcing
     Kilted's setup.bash is undone and `import rclpy` fails.
  3. The Pi's system mosquitto service (port 1883) binds localhost only;
     the E5 broker is a dedicated instance with `listener 1884 0.0.0.0`
     (as E2/E4, plus the LAN bind).
  4. `eval/common/proc_sampler.py` reads `/proc`, which macOS lacks — the
     Mac-side resource sampler still needs a `ps`-based variant (open
     work item for the E5 harness).

### Results

**Implementation.** The E4 robot model, fleet launch, mission, speed
properties, and separation property were reused unchanged. The generated E5
deployment places Gazebo/Nav2 on the PC, the seven-source monitor and a
dedicated Mosquitto instance on the Pi, and the property graph in a native
Python process on the Mac. A second runner on the Pi consumes the same MQTT
stream as an evaluation control; its outputs are compared directly with the
Mac outputs, so distribution transparency is tested on one identical input
stream rather than inferred from a separate E4 trajectory. The Mac runner is
kept below a live SSH parent for the complete run, as required by the macOS
Local Network behavior found during preparation.

Two measurement additions make the physical links explicit. First,
`eval/e5/dds_probe.py` publishes a 5 Hz `PoseStamped` whose header contains
the PC wall clock. Nav2 headers use simulation time and cannot provide this
measurement. Comparing that header with the Pi collection timestamp gives
the PC-to-Pi DDS/LAN delay. Second, `measure_clock.py` estimates Pi-minus-PC
and Mac-minus-PC offsets over persistent SSH exchanges at the start and end
of the run. All cross-host latency figures subtract those offsets and report
the estimator uncertainty. A portable `ps`-based process-tree sampler was
added for macOS and for the PC launch tree; the Pi retains the `/proc`
sampler. MQTT sources now log separate data/bookend receive counts, allowing
the harness to check the complete transported record stream, not only the
records that trigger verdicts.

**Reference run** — headless, SEP_MIN 1.0 m, SPEED_MAX 0.3 m/s,
2026-07-14 (`eval/e5/results/run_20260714_000656/`):

| Check | Outcome |
|---|---|
| Three-machine pipeline | PC Gazebo/2x Nav2 -> DDS/LAN -> Pi monitor/broker -> MQTT/LAN -> Mac runner; no fallback used |
| Mission | 4/4 goals SUCCEEDED (leg 1: robot2 24.6 s, robot1 35.9 s; leg 2: robot1 28.1 s, robot2 30.5 s) |
| Mac speed verdicts vs. Pi record oracle | robot1 12/12; robot2 18/18; precision/recall 1.0 |
| Fleet separation vs. replay oracle | 4/4 transitions exact; one violation/recovery period in each mission leg |
| Pi-reference vs. Mac verdicts | all three streams identical: 12/12, 18/18, and 4/4 on property, result, and `input_record_ids` |
| MQTT delivery | Pi published 4173 data records; Pi reference received 4173 and Mac received 4173 (zero loss at both subscribers) |
| Gazebo ground truth | 2/2 physical sub-1.0 m periods matched; AMCL/physical minimum 0.547/0.621 m; 4/4 final physical poses within 0.10 m |
| DDS PC publish -> Pi collect | 506 probes; mean 0.668 ms, median 0.595 ms, p95 1.044 ms, max 2.449 ms |
| MQTT Pi collect -> Mac verdict (clock-corrected) | mean 4.026/3.665/3.458 ms for robot1 speed / robot2 speed / separation |
| Pi-local MQTT reference latency | mean 1.154/1.231/1.328 ms; the Mac path adds 2.13--2.87 ms depending on property |
| MQTT application payload | 18.245 Mbit fleet data, 173.6 kbit/s over 105.1 s; 197.0 kbit/s including the DDS measurement probe; protocol headers excluded |
| PC Nav2/Gazebo process tree | 354.2 % CPU (3.54 cores) mean, 1.47 GB maximum RSS |
| Pi monitor + reference runner | 12.73 % CPU mean, 113.4 MB combined maximum RSS (monitor alone: 12.46 %, 88.4 MB) |
| Mac verdict runner | 1.41 % CPU mean, 27.5 MB maximum RSS |

The run collected 4173 records: 3667 from the unchanged E4 sources and 506
from the latency probe. There were zero sequence gaps on the probe, both
command streams, and both AMCL streams. Each odometry stream had 2418 gaps by
design because `RateThrottler` reduced it to about 4.83 Hz before file and
MQTT export.

**Clock qualification.** Pi-minus-PC changed from +1.256 to +1.397 ms and
Mac-minus-PC from +2.373 to +3.018 ms during the run. The mean Mac-minus-Pi
offset subtracted from verdict latency was +1.369 ms. The maximum clock drift
during the measured interval was 0.645 ms (Mac vs. PC). The SSH midpoint
estimator bounded Pi offset uncertainty at 0.099 ms and the combined
Mac-minus-Pi offset uncertainty at 1.926 ms. The corrected Mac latency should
therefore be read at millisecond, not sub-millisecond, precision; this is the
explicit qualification required by the preparation probe's NTP observation.

**Observations.** Physical placement changed only generated connection and
output parameters; the E4 converters and verdict services needed no code
changes. The Pi handled DDS collection, JSONL export, MQTT publication, and
the reference evaluation at roughly one eighth of one CPU core on average.
The Mac received the full record stream despite having no ROS installation.
The Mac missed only the initial session-start bookend because it deliberately
subscribed after the Pi monitor started; it received every data record and the
session-end bookend, so this does not affect loss or correctness.

**Conclusions.** (RQ2) Moving the same evaluation graph from the Pi control
to the Mac preserved all 34 verdict transitions and their causal record
attribution exactly. The added physical-network path cost approximately
2.1--2.9 ms beyond the Pi-local MQTT reference at this workload. (RQ6) The
complete pipeline sustained the two-robot Nav2 mission across Ubuntu x86-64,
Ubuntu aarch64, and macOS arm64, with zero transported data loss and modest
monitor/verifier resource use. Direct PC-to-Pi DDS worked for the full run, so
the planned monitor-on-PC fallback was not used. These results establish the
claimed heterogeneous LAN deployment; they do not generalize to WAN links,
larger fleets, or long-duration fault tolerance.

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
