# E4 through the WebUI (interactive replay)

This playbook re-creates the E4 fleet-separation experiment (two
TurtleBot3/Nav2 robots on crossing patrol routes) interactively in the
WebUI. Unlike the headless `run.sh` reference, the robots patrol the two
crossing legs **in an endless loop** until you press Stop, and the
monitoring runtimes are placed and started from the topology playground.

In Local Mode everything runs **natively** on this machine: the ROS
application and the generated monitoring runtime are host processes (GUI
applications such as Gazebo/RViz need the real display, and under Docker
Desktop containers cannot join the host DDS graph anyway). Docker is used
only by LAN mode to run runtimes on remote SSH hosts.

## 1. Start the WebUI service

From a terminal with ROS sourced (system Python, not the `.venv`):

```bash
cd ~/ROS2-Monitor-Infra
set +u; source /opt/ros/kilted/setup.bash; source ~/ros2_ws/install/setup.bash; set -u
python3 webui/server.py
```

Open <http://127.0.0.1:8765>. Stay in **Local Mode**.

ROS must be sourced in this terminal: the server inherits the environment to
the natively spawned monitor runtime and to graph scanning.

## 2. Create the host

**New Host** once; select the box and rename via *Host id* to `e4`.

Everything — the ROS 2 collection, the monitor, the separation converter,
and the separation verdict — runs inside this one host as a single
`monitor_node` process. With one host there are no cross-host links, so no
MQTT broker block appears and none is needed: records flow to the converter
and the verdict in-process.

## 3. Start the ROS application (Gazebo + RViz)

1. Select the `e4` host. In the *ROS application* section set the start
   command to:

   ```
   eval/e4/run_loop.sh
   ```

2. With the host still selected, press **Start** (toolbar). A Gazebo window
   and two RViz windows open; bringup takes 1–2 minutes (watch the *Live
   log* tab — it announces localization, initial poses, navigation). Prefix
   the command with `USE_GZ_GUI=False` or `USE_RVIZ=False` to disable the
   windows.
3. When the log prints `starting the endless crossing patrol`, the two
   robots repeat the E4 crossing legs forever ("dead loop") until you stop
   them from the UI.

## 4. Scan and declare the observed sources

Press **Scan graph**. Keep the `e4` host selected and add these two topics
from the results drawer (the search box filters):

- `/robot1/amcl_pose` (`geometry_msgs/msg/PoseWithCovarianceStamped`)
- `/robot2/amcl_pose` (`geometry_msgs/msg/PoseWithCovarianceStamped`)

If a scan shows only one robot's topics, scan again — a fresh discovery
node needs a moment for DDS discovery to converge.

## 5. Build the runtimes

All blocks go on the `e4` host:

1. **+ Monitor** → id `monitor_e4`. Select the two source blocks (click,
   then shift-click), shift-click the monitor block last, press **Connect**.
2. **+ Converter** → `separation`: manifest *Separation Distance Converter*
   (no params; it learns `/robot1` and `/robot2` from the `amcl_pose`
   source names). Connect both `amcl_pose` sources → `separation`.
3. **+ Verdict** → `separation_check`: *Separation Distance Verdict*,
   minimum separation `1.0`. Connect `separation` → `separation_check`.

## 6. Start the runtimes and observe

Click empty playground space (nothing selected) and press **Start**. This
generates `generated/showcase/e4.yaml` and launches one `monitor_node` host
process running the whole chain.

In the *Live log* you should see `fleet_separation` flip to `false` at each
corridor crossing (distance < 1.0 m) and recover to `true` after the robots
pass — once per patrol lap. Verdict files accumulate under
`output/showcase/e4/verdicts_*.jsonl`.

The *Code* tab follows the selection: selecting the host shows the
generated `e4.yaml`; selecting the converter or verdict block shows a
**Plugin / YAML** dropdown — *Plugin* is the block's plugin source
(`custom/separation_converter.py`, `custom/separation_verdict.py`), *YAML*
is the generated file of the host it runs in.

## 7. Stop everything

1. Nothing selected → **Stop**: ends the monitor process and interrupts the
   application — the mission cancels in-flight goals, Gazebo/RViz close,
   and `eval/e4/cleanup.sh` purges any leftovers.
2. Selecting only the `e4` host and pressing **Stop** stops the application
   alone; selecting only runtime blocks stops just the monitor process.

If a Gazebo session ever hangs (or the WebUI server was killed while the
simulation ran), run `eval/e4/cleanup.sh` manually.

## Troubleshooting

- **Bringup stalls at "waiting for both navigation stacks", no windows,
  `nav2.log` shows `X Error ... GLX` or RViz `Failed to create an OpenGL
  context`**: OpenGL is broken system-wide, typically because an NVIDIA
  driver update left the old kernel module loaded (`nvidia-smi` then says
  "Driver/library version mismatch"). Reboot the machine and retry. The
  Gazebo *server* also needs OpenGL (GPU lidar), so this breaks the
  simulation even without any window.
- A stuck or half-started simulation session: press Stop on the host, and
  if leftovers remain run `eval/e4/cleanup.sh`.

## Notes

- The runtimes can also be split across several hosts (e.g. separate
  `monitor` / `converter` / `checker` boxes) — cross-host links then flow
  over MQTT and a broker block appears. The single-host layout above is the
  simplest local setup.
- The ros2 source block always executes inside the monitor's process
  (`monitor_node` is the ROS 2 interface); converters and verdict services
  are the units that can be placed on their own hosts/processes.
- The per-robot speed chains from the headless E4 (*Command Speed
  Converter* with `speed_path` = `twist.linear.x` on `/robotN/cmd_vel`,
  *Threshold Verdict* at `0.3`) can be added to the same host in the same
  way.
- `USE_GZ_GUI=False USE_RVIZ=False eval/e4/run_loop.sh` as the start
  command runs the same loop fully headless.
- The headless reference experiment with offline oracle checks remains
  `eval/e4/run.sh`; this playbook is for interactive demonstration.
