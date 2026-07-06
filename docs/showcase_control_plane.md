# ROS2-Monitor-Infra-Dashboard

This is the first incremental step toward a demonstrable ROS2-Monitor-Infra
project UI. It wraps the existing runtime instead of replacing it. The intended
flow is:

```text
Start robot container -> scan graph -> select monitored sources
-> configure converter/verdict nodes and links -> start monitor
```

## Run

From the repository root:

```bash
python webui/server.py
```

Open <http://127.0.0.1:8765>.

If you override the port and see a page such as `Welcome to nginx!`, that port
is already owned by another local service. Pick another port, for example:

```bash
python webui/server.py --port 8766
```

The server uses only the Python standard library plus the dependencies already
used by the project. It serves a static frontend and a small local API.

The dashboard can start the demo robot container from the **Start Robots** tab.
For Docker Desktop demos, both the robot and monitor containers use host
networking and host IPC so Fast DDS shared-memory transport works across
containers:

```bash
docker run --rm -it --network host --ipc=host \
  -e ROS_DOMAIN_ID=0 \
  -v "$PWD/demo/common:/demo/common:ro" \
  ros2-monitor-infra \
  /bin/bash -lc "source /opt/ros/kilted/setup.bash && python3 /demo/common/topic_robot.py cmd-velocity-cycle --ros-args -r __node:=showcase_robot"
```

To inspect different ROS resource kinds, replace the dashboard **Start command**
with one of these independent demos:

```bash
source /opt/ros/kilted/setup.bash && python3 /demo/common/service_simulator.py --ros-args -r __node:=showcase_service_robot
```

```bash
source /opt/ros/kilted/setup.bash && python3 /demo/common/action_simulator.py --ros-args -r __node:=showcase_action_robot
```

## What Works Now

- Starts and stops a robot container from a Dockerfile path and container start
  command, and streams robot container status/logs through Server-Sent Events.
- Scans the ROS graph through local `rclpy` when available, otherwise tries the
  project Docker Compose `monitor` service.
- Lets the user add multiple monitored topic, service, and action sources.
- Lists a small set of plugin presets based on `custom/` plugins, including a
  four-host two-robot relative-speed preset.
- Reads plugin manifests from `custom/manifests/` and renders typed parameter
  fields without treating any converter/verdict kwargs as framework-wide keys.
- Configures converter nodes, verdict-service nodes, source-to-converter links,
  and converter-to-verdict links separately.
- Places every source, converter, and verdict service on a named host; edges
  that cross hosts become MQTT links over a configurable broker, same-host
  edges run in-process.
- Builds a generation-request JSON from the form when the monitor starts.
- Calls `monitor/config_gen.py`, writes runtime YAML under `generated/showcase/`,
  and shows the generated JSON/YAML in the Monitor tab.
- Writes `generated/showcase/docker-compose.yml`.
- Starts and stops the generated monitor compose. The generated compose uses
  `network_mode: host` and `ipc: host` so it can monitor a separately started
  ROS 2 app container that uses the same settings.
- Streams compose logs and recent verdict JSONL files under `output/showcase/`
  through Server-Sent Events.
- Clears dashboard verdict JSONL records from `output/showcase/` and
  `generated/showcase/`.

## Deployment Topologies

The Dashboard no longer selects from fixed modes. Topology follows from host
placement:

| Placement | Generated runtimes |
|---|---|
| Everything on one host | One `monitor_node` runtime with in-process graph wiring (traditional / all-in-one). |
| Sources on robot host(s), converters+verdicts elsewhere | Per-robot `monitor_node` publishing DataRecords over MQTT plus `node_runner` hosts running the evaluation graph (orchestrated). |
| Converter and verdict on separate hosts | The converter host publishes DSL records through a dsl output endpoint; the verdict host consumes them through a dsl input endpoint. |
| Multiple robots feeding one converter | One records input per distinct transport namespace; same-broker feeds are merged automatically. |

Chapter 4's monitoring organisations map onto these placements; decentralised
and choreographed organisations additionally need coordination semantics that
the Dashboard does not model yet.

## Local Mode and LAN Mode

The dashboard has two modes, switched with the **Local Mode / LAN Mode**
toggle in the toolbar (server state, `GET/POST /api/mode`). Local Mode is the
original behaviour: every placement host becomes a service in one generated
Docker Compose file on this machine.

In LAN Mode a host is either `local` (the machine running the dashboard) or a
machine validated over SSH. Free-form host creation is disabled; the **Add SSH
Host** dialog asks for an address such as `user@hostname.local`:

1. Key-based SSH is attempted first (`BatchMode`). If it fails, the dialog
   asks for the password once and the server installs the local public key
   into the host's `authorized_keys` through an `SSH_ASKPASS` helper (no
   sshpass/paramiko dependency). All later operations are passwordless.
2. The host is probed for OS, home directory, and a working Docker daemon,
   then persisted in `generated/lan_hosts.json`.

Deployment per SSH host:

- The project is copied to `~/ROS2-Monitor-Infra` on the host with
  `rsync -az --delete` (excluding `.git`, `.venv`, `output/`, etc.).
- Each SSH host gets its own `generated/showcase/docker-compose.<host>.yml`
  with only that host's runtime; it is started remotely with
  `docker compose up --build -d` inside the host's project copy. The first
  start builds the image there and can take several minutes.
- Services placed on `local` (plus the mosquitto broker whenever a cross-host
  link exists) stay in `generated/showcase/docker-compose.yml` and run here.
- A loopback broker address is automatically replaced with this machine's LAN
  IP so remote runtimes can reach it. In LAN mode the mosquitto broker uses a
  published port instead of host networking, because with Docker Desktop host
  networking stays inside its VM (loopback forwarding only) while published
  ports are exposed on the real host interface. The UI defaults the LAN
  broker port to 1884 to avoid clashing with a system mosquitto on 1883; the
  port must be allowed through the local firewall.
- Remote compose logs stream over SSH into the Live log pane, and
  `output/showcase/` is rsync-pulled back every two seconds so remote verdicts
  appear in the dashboard.

macOS constraint: Docker Desktop runs containers inside a VM, so
`network_mode: host`/`ipc: host` cannot join the LAN ROS graph. macOS hosts
are therefore limited to converter and verdict runtimes (MQTT only, bridge
networking); ROS sources and monitor runtimes must stay on Linux hosts. The
UI blocks such placements and generation rejects them. Robot demo containers
always start on the local machine.

## Current Guardrails

- The robot start command is executed inside the configured Docker container.
- Monitor runtime execution is limited to generated Dashboard compose files.
- The generated monitor does not start a built-in ROS 2 app. Start the ROS 2
  application first, then scan, configure, and start the monitor.
- Service monitoring depends on the service server publishing ROS 2 service
  introspection events. Without introspection, the generated monitor subscribes
  successfully but receives no service records.
- Action monitoring currently uses the runtime's supported hidden action
  streams: feedback and status.
- Custom Python plugin authoring is outside the dashboard scope. The UI uses
  plugin manifests and existing Python classes.
- Runtime updates are restart-oriented: changing configuration regenerates files
  and restarts the monitor.

## Roadmap

1. Add decentralised and choreographed presets once their runtime
   coordination semantics are explicit.
2. Make restart-on-change explicit in the Monitor tab.
3. Add richer Service/Action controls for service phases and action phase
   selection once the UI needs those finer-grained runtime knobs.
