# Deployment Demo Test Report

Date: 2026-06-09

## Objective

Demonstrate breadth of runtime-verification deployment organisations for ROS 2
without claiming production guarantees for ordering, clock synchronisation,
fault tolerance, security, or large-scale performance.

## Test environment

- Windows host with Docker Desktop 4.77.0
- Docker Engine 29.5.3, Linux/amd64 containers
- Docker Compose 5.1.4
- ROS 2 Kilted base image
- Eclipse Mosquitto 2

Every Compose demo independently starts its synthetic robot publisher and all
required monitoring components. Robot-side publishers are co-located with
their monitor in one container. This models one robot location and avoids
Docker Desktop multicast limitations. Communication between robot locations
and verifier locations uses MQTT.

## Verified deployments

| Demo | Organisation | Expected evidence | Result |
|---|---|---|---|
| `deploy_mode1` | Traditional local | local speed violation/recovery cycle | Pass |
| `deploy_mode2` | Orchestrated, host network | central speed violation/recovery cycle | Pass |
| `deploy_mode3` | Orchestrated, split networks, MQTT verdict output | central cycle and MQTT verdict exporter connection | Pass |
| `nav2_compatible_local` | Nav2-interface-compatible local | `/cmd_vel` violation/recovery cycle | Pass |
| `deploy_mode4_hybrid` | Local and central evaluation | matching cycles at both locations | Pass |
| `multi_robot_orchestrated` | Two robot traces, central isolated rules | separate cycles for both robots | Pass |
| `multi_robot_global` | Central global multi-trace predicate | distance violation/recovery cycle | Pass |
| `choreographed_verdicts` | Local verdict aggregation | local and aggregate cycles | Pass |
| `offline_replay` | Live recording followed by offline monitoring | replayed speed cycle | Pass |

## Key observed evidence

- Nav2-compatible case observed `/odom` and `/cmd_vel`, then emitted a
  violation for `/cmd_vel = 0.45`.
- Hybrid case emitted the same correlated input record as a local verdict and
  a central verdict.
- Multi-robot orchestrated case emitted independent violation/recovery cycles
  for both robots.
- Global predicate case alternated fleet distance between `0.5m` and `1.5m`,
  producing violation and recovery.
- Choreographed prototype sent local verdicts rather than raw traces to its
  aggregator, which emitted a fleet-level violation after both local
  violations became active.
- Offline replay started a robot, recorded its live `/odom` DataRecords, then
  replayed that generated trace and emitted a violation.

## Automated and unit validation

- Host-side unit suite excluding the ROS-only collection test: `117 passed`.
- Full unit suite inside a sourced ROS 2 Linux container: `121 passed`.
- All new Compose files pass `docker compose config`.
- `demo/verify_demos.ps1` runs all nine self-contained deployment cases and
  requires both violation and recovery verdicts in every case.

## Fixes found during testing

- Changed mode 3 host MQTT port from `1883` to `2883`; the Windows test host
  reserves a dynamic range containing `1883`.
- Quoted YAML paths containing `{session_id}` inside flow mappings.
- Replaced the parameterised demo robot with four fixed, readable scenarios.

## Nav2 scope

`nav2_compatible_local` uses real ROS 2 message interfaces relevant to Nav2
(`/odom` and `/cmd_vel`) and can be pointed at a real Nav2 graph without
changing the monitor rule. It is not a complete Nav2 bringup: a full headless
Nav2 experiment additionally requires navigation packages, lifecycle
configuration, map/localisation inputs, and usually a simulator.

## Known research-prototype limitations

- No guarantee for message loss, duplication, ordering, or clock alignment.
- Global properties operate on the latest received values.
- Monitor decomposition is manually configured.
- Choreographed aggregation combines local Boolean verdicts, not automatically
  decomposed temporal formulas.
- File replay loops over the growing demo recording until stopped.

These limitations are suitable candidates for the paper's future-work section.

## Reproducing the tests

From the repository root in PowerShell:

```powershell
docker version
pytest -q --ignore=test/unit/test_monitor_node_service_discovery.py
.\demo\verify_demos.ps1
```

To inspect one case:

```powershell
docker compose -f demo\multi_robot_global\docker-compose.yml up --build
```

In another terminal:

```powershell
docker compose -f demo\multi_robot_global\docker-compose.yml logs -f
docker compose -f demo\multi_robot_global\docker-compose.yml down
```

Verdict JSONL files are written below `output/`.
