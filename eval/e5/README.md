# E5 — Heterogeneous three-machine LAN deployment

E5 repeats the E4 two-robot Nav2 mission while placing the three runtime
roles on different physical machines:

```text
Ubuntu PC                       Raspberry Pi                 MacBook
Gazebo + 2x Nav2 -- DDS/LAN --> monitor_node -- MQTT/LAN --> node_runner
                                      |
                                Mosquitto :1884
                                      |
                              Pi reference runner
```

The Pi reference runner and the Mac runner receive the same MQTT record
stream. Their three verdict files are compared on property, result, and
contributing record identifiers. The reference runner is an evaluation
control only; the E5 deployment claim uses the Mac as its verdict tier.

## Run

The machines and dependencies in `../PLAN.md` section 8 must be prepared.
From the Ubuntu PC repository root:

```bash
eval/e5/run.sh
```

Defaults can be overridden without editing the experiment:

```bash
PI_HOST=pi@raspberrypi.local \
MAC_HOST=user@macbook.local \
BROKER=192.168.2.18 \
SEP_MIN=1.0 SPEED_MAX=0.3 CANCEL_AFTER=120 \
eval/e5/run.sh
```

The run is headless by default. `USE_RVIZ=True` is only for an optional
illustration run and is not part of the evidence-producing control flow.

For an interactive replay placed and started from the WebUI topology
playground (LAN mode, native SSH execution), see [`WEBUI.md`](WEBUI.md).
For a no-SSH illustration run in which the three machines are started from
their own terminals and the PC displays Gazebo plus two RViz windows, follow
[`MANUAL_GUI.md`](MANUAL_GUI.md). The wrappers in `manual/` enforce a shared,
fresh run identifier and preserve the same ordered distributed shutdown used
by the automated harness.

`run.sh` synchronizes the current working tree to
`~/ROS2-Monitor-Infra` on both remote machines, excluding Git metadata,
result directories, virtual environments, and the thesis. It generates the
three runtime YAML files from `request.json`, starts the Pi and Mac tiers
under live SSH sessions, runs the E4 mission on the PC, performs ordered
shutdown, retrieves remote artifacts, and runs all correctness checks.

The Mac SSH session must remain alive for the whole run. On the prepared
macOS 15 host, Local Network privacy silently prevents an orphaned detached
runner from opening the broker connection.

If a run is interrupted, request targeted cleanup with:

```bash
eval/e5/cleanup.sh
```

## Evidence and metrics

Each run is stored under `eval/e5/results/run_<timestamp>/` with `pc/`,
`pi/`, `pi_reference/`, `mac/`, and generated `config/` subdirectories.
The top-level reports include:

- `metrics_speed_r{1,2}_remote.json`: Mac verdicts against the recorded Pi
  input oracle, with measured Mac-minus-Pi clock correction;
- `separation_remote.json` and `gt.json`: fleet property against replay and
  Gazebo physical ground truth;
- `transparency_*.json`: Pi-reference versus Mac verdict equality;
- `metrics_e5.json`: clock offsets and uncertainty, DDS PC-to-Pi latency,
  MQTT Pi-to-Pi and Pi-to-Mac latency, MQTT data counts and application
  payload bandwidth, source sequence counts, and per-machine CPU/RSS.

Nav2 uses simulation time, so E5 also publishes `/e5/dds_probe` at 5 Hz.
Its `PoseStamped.header.stamp` is the PC wall clock and its Pi
`DataRecord.timestamp` is the collection clock. This permits a clock-corrected
measurement of the DDS/LAN segment without changing or feeding the monitored
fleet properties.

The MQTT bandwidth value is the serialized DataRecord payload size divided by
run duration. It intentionally excludes MQTT, TCP, IP, and link-layer headers.
Clock offsets are measured at both ends of the run over one persistent SSH
exchange per host and are reported with midpoint-estimator uncertainty.

Plan and reference results: [`../PLAN.md`](../PLAN.md), section 8.

## Reference result

The headless run `run_20260714_000656` completed with status 0. The Pi
published 4,173 data records and both the Pi reference and Mac received all
4,173. The Mac speed streams matched 12/12 and 18/18 offline transitions; the
four fleet-separation transitions matched both replay and two Gazebo physical
violation periods. All three Mac verdict streams were identical to the Pi
reference streams. Clock-corrected mean latency was 0.668 ms for the PC-to-Pi
DDS probe and 3.46--4.03 ms from Pi collection to Mac verdict export. Full
metrics and their clock qualification are recorded in `../PLAN.md` section 8.
