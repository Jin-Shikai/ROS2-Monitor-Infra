# E5 through the WebUI (three machines, interactive replay)

This playbook repeats the E5 placement interactively from the WebUI's LAN
mode: the Ubuntu workstation runs the ROS application (Gazebo + two Nav2
stacks + endless crossing patrol), the Raspberry Pi runs the monitor and
the MQTT broker, and the MacBook runs the checker (converter + verdict,
no ROS 2). All runtimes run **natively** on their machines — the WebUI
pushes the project over rsync and starts each runtime under a live SSH
session, exactly like the headless `run.sh` tiers did.

Machine preparation is the thesis E5 setup (`../PLAN.md` section 8): the
Pi has ROS 2 Kilted, mosquitto, and paho; the Mac has a Homebrew
python3.12 with paho and PyYAML; both are reachable over SSH on the LAN.

## 1. Start the WebUI and switch to LAN Mode

From a terminal with ROS sourced (system Python, not the `.venv`):

```bash
cd ~/ROS2-Monitor-Infra
set +u; source /opt/ros/kilted/setup.bash; source ~/ros2_ws/install/setup.bash; set -u
python3 webui/server.py
```

Open <http://127.0.0.1:8765> and switch the mode toggle to **LAN Mode**.

## 2. Add the hosts

Switching to LAN Mode places a `local` host box (the workstation). Then
**Add SSH Host** twice — each registration adds its host box:

- `pi@raspberrypi.local` → host box `raspberrypi_local`
- `user@macbook.local` → host box `macbook_local`

If key authentication is not set up yet, the dialog asks once for the
password and installs the local public key. Each host shows `ssh ✓` when
ready. The macOS host is checker-only (no ROS 2 there).

## 3. Start the ROS application

Select the `local` host, set the *ROS application* start command to

```
eval/e4/run_loop.sh
```

and press **Start**. Gazebo and the two RViz windows appear on the
workstation; wait for `starting the endless crossing patrol` in the Live
log (1–2 minutes). E5 runs the same mission as E4 — only the monitoring
placement changes.

## 4. Declare sources and build the runtimes

1. **Scan graph**. Select the `raspberrypi_local` host box and declare:
   - `/robot1/amcl_pose` (`geometry_msgs/msg/PoseWithCovarianceStamped`)
   - `/robot2/amcl_pose` (`geometry_msgs/msg/PoseWithCovarianceStamped`)
2. **+ Monitor** → id `monitor_e5`, host `raspberrypi_local`. Connect both
   sources → monitor.
3. **+ Converter** → `separation`, manifest *Separation Distance
   Converter*, host `macbook_local`. Connect both `amcl_pose`
   sources → `separation`.
4. **+ Verdict** → `separation_check`, *Separation Distance Verdict*,
   minimum separation `1.0`, host `macbook_local`. Connect
   `separation` → `separation_check`.
5. Select the broker block and set **Broker host** to `raspberrypi_local`
   and **port** to `1884` (the links then carry the Pi's numeric LAN
   address, e.g. `192.168.2.18:1884` — macOS resolves `.local` names
   only for approved binaries. The Pi's system mosquitto holds 1883, so
   keep 1884).

## 5. Start and observe

Click empty playground space and press **Start**. The WebUI then:

1. rsyncs the project to the Pi and starts `mosquitto` there on 1884;
2. starts `node_runner` on the Mac (Homebrew python3.12) under a live
   SSH session — macOS Local Network privacy requires exactly that;
3. starts `monitor_node` on the Pi (ROS sourced, DDS with the
   workstation).

The Live log streams all three over their SSH sessions; select a block
to filter (converter I/O and verdicts appear under their runtime blocks
as in local mode). `fleet_separation` flips to `false` at each corridor
crossing and back to `true` after the robots pass.

Verdict files are written on the Mac and rsync-pulled back every 2 s to
`output/showcase/macbook_local/verdicts_*.jsonl` (the full content
lands at stop, when the runner flushes its exporters).

## 6. Stop

Nothing selected → **Stop**. Order: the Pi monitor stops first, the Mac
runner drains and stops, the Pi broker stops last, and the ROS
application is interrupted (mission cancels goals, cleanup runs). A
final rsync pull retrieves the last verdicts.

## Troubleshooting

- **Mac runner starts but never logs `MQTTSource connected` and the
  verdict file stays empty**: macOS Local Network privacy is blocking
  the Homebrew python binary. A `socket.create_connection` to the Pi
  from `/opt/homebrew/bin/python3.12` then fails with
  `[Errno 65] No route to host` while Apple's own `nc`/`python3`
  succeed. The grant is per binary and a Homebrew python upgrade
  silently drops it, with no prompt for SSH-launched processes. Fix on
  the MacBook: System Settings → Privacy & Security → **Local Network**
  → enable Python, then restart the runtimes. This also affects the
  headless `run.sh` after any brew python upgrade.
- **Mac runner cannot reach the broker even with the grant**: it must
  run under a live SSH session (macOS 15 also blocks LAN TCP from
  orphaned processes). The WebUI keeps the session alive itself; do not
  start the runner manually with `nohup`.
- **First start is slow**: the initial rsync ships the project to both
  machines; later starts only transfer changes.
- **Scan shows only one robot's topics**: scan again — a fresh discovery
  node needs a moment for DDS to converge.
- **No records on the Pi**: check that both machines are on the same
  LAN/subnet (DDS discovery) and that the workstation terminal running
  the WebUI has ROS sourced.
- The full E5 property set (per-robot speed on `/robotN/cmd_vel`) can be
  added the same way: *Command Speed Converter* (`speed_path` =
  `twist.linear.x`) + *Threshold Verdict* `0.3` on the Mac host.
- The headless, evidence-producing E5 remains `eval/e5/run.sh`; this
  playbook is the interactive demonstration.
