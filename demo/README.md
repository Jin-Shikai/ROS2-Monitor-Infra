# Deployment demo matrix

| Demo | Monitoring organisation |
|---|---|
| `deploy_mode1` | Traditional robot-side all-in-one |
| `deploy_mode2` | Orchestrated split monitor/verifier on host network |
| `deploy_mode3` | Orchestrated split network topology |
| `nav2_compatible_local` | Nav2-interface-compatible local monitoring |
| `deploy_mode4_hybrid` | Local and central verification in parallel |
| `multi_robot_orchestrated` | Multiple robot traces, central isolated properties |
| `multi_robot_global` | Central global predicate over two robot traces |
| `choreographed_verdicts` | Local verdicts combined into a fleet verdict |
| `offline_replay` | Live robot recording followed by offline monitoring |

Every demo is self-testing and independently starts at least one synthetic
ROS2 robot publisher plus the monitor components needed to observe its
actions. Robot-side publishers and monitors are co-located to represent one
robot location and avoid Docker Desktop multicast limitations; communication
between locations uses MQTT. `offline_replay` first records a newly started
robot, then verifies the resulting file in a separate process.

Shared demo fixtures live under `demo/common/`. `robot_simulator.py` provides
four fixed, named scenarios rather than a collection of behavior switches.
Each monitored property repeatedly alternates between violation and recovery,
so the logs remain active and the test meaning is visible.

Run the self-contained suite from PowerShell:

```powershell
.\demo\verify_demos.ps1
```

See `docs/DEPLOYMENT_TEST_REPORT.md` for verified evidence and limitations.
