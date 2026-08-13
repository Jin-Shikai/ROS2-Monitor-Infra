# ROS2-Monitor-Infra

Configurable runtime monitoring and verification infrastructure for ROS 2.
It observes topics, services, and actions of an unmodified ROS 2 application,
converts the observations into property-specific records, and evaluates
verdicts locally or across distributed hosts connected by MQTT.

## Components

| Directory | Contents |
|---|---|
| `monitor/` | Core runtime. `monitor_node.py` (collection tier, needs ROS 2), `node_runner.py` (evaluation tier, no ROS required), `config_gen.py` (projects a deployment JSON request into runtime YAML). |
| `custom/` | Converter and verdict-service plugins plus dashboard manifests. |
| `webui/` | Dashboard: scan the ROS graph, place components on hosts, generate and launch monitor deployments (local Docker Compose or LAN via SSH). |
| `demo/` | ROS 2 robot fixtures used by the dashboard presets. |
| `docs/` | Configuration spec, DataRecord/DSL record specs, DSL adaptation guide, config generation algorithm. |
| `eval/` | Five evaluation experiments (E1–E5), from local baseline to a heterogeneous three-machine LAN deployment. See `eval/PLAN.md`. |
| `test/` | Unit and component tests (`pytest`). |

## Quick start

Requirements: Python 3.12+, `paho-mqtt`, `pyyaml`. The collection tier needs
ROS 2 (Kilted); the evaluation tier and dashboard run anywhere.

Run the dashboard:

```bash
python webui/server.py
```

Run a monitor directly from a runtime YAML:

```bash
python monitor/monitor_node.py -c monitor/config.yaml   # collection + evaluation
python monitor/node_runner.py -c <runner.yaml>          # evaluation only
```

Or bring up the containerized monitor:

```bash
docker compose up --build
```

Run the tests:

```bash
pytest
```

