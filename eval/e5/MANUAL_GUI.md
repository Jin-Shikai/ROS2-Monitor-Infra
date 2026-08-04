# E5 manual three-machine GUI run

This procedure runs the E5 roles directly from a local terminal on each
machine. It uses no SSH for orchestration. The PC displays Gazebo and two RViz
windows; the Pi collects ROS 2 data and publishes it through Mosquitto; the Mac
evaluates the received stream. The Pi also runs the reference verifier used by
the automated E5 comparison.

This is the illustration workflow. Keep the completed headless run as the
quantitative result: Gazebo/RViz rendering changes PC resource use, and this
manual workflow does not make the SSH midpoint clock measurements required to
qualify cross-machine latency.

## Before starting

Use one fresh identifier on all three machines. Do not let each machine expand
`$(date ...)` independently, because even a one-second difference creates
three unrelated result directories. For example:

```bash
RUN_ID=run_gui_20260715_120000
```

The repository must be at `~/ROS2-Monitor-Infra` on the Pi and Mac and at the
current project path on the Ubuntu PC. The prepared defaults are broker
`192.168.2.18:1884`, separation threshold `1.0 m`, and speed threshold
`0.3 m/s`. They can be overridden consistently on every `start` command with
`BROKER=... SEP_MIN=... SPEED_MAX=...`.

Start each role from an interactive desktop or login terminal and leave its
`start` terminal open. In particular, do not launch the Mac role through
`nohup`: macOS 15 Local Network privacy can prevent an orphaned process from
opening the LAN broker connection.

## Start order

### 1. Raspberry Pi: transport and collection tier

```bash
cd ~/ROS2-Monitor-Infra
eval/e5/manual/pi.sh start run_gui_20260715_120000
```

Wait for `E5_PI_READY`. This terminal owns Mosquitto, `monitor_node`, the
Pi-local reference runner, and their process sampler.

Optional inspection from a second Pi terminal:

```bash
cd ~/ROS2-Monitor-Infra
eval/e5/manual/pi.sh status run_gui_20260715_120000
tail -F eval/e5/results/run_gui_20260715_120000/pi/monitor.log
```

The monitor log should contain `Registered 7 collector(s); spinning.`. The
broker first sees the Pi publishers/subscriber, then a third client when the
Mac joins.

### 2. Mac: verdict tier

```bash
cd ~/ROS2-Monitor-Infra
eval/e5/manual/mac.sh start run_gui_20260715_120000
```

Wait for `E5_MAC_READY`. The start terminal must remain open. The runner's
stdout is stored in `mac/runner.log`, so use a second terminal to watch the
live fleet-separation verdicts:

```bash
cd ~/ROS2-Monitor-Infra
tail -F eval/e5/results/run_gui_20260715_120000/mac/runner.log
```

The first connection line should report an MQTT subscription to
`monitor/e5/#` on the Pi broker.

### 3. Ubuntu PC: simulation, Nav2, RViz, and publishers

Run this from the PC graphical desktop session:

```bash
cd ~/ROS2-Monitor-Infra
eval/e5/manual/pc.sh start run_gui_20260715_120000
```

The script starts the Gazebo server, a Gazebo GUI client, two namespaced Nav2
stacks, two RViz windows, the 5 Hz DDS wall-clock probe, and the Gazebo
ground-truth logger. It publishes the two initial poses and waits for all four
localization/navigation lifecycle groups. Wait for `E5_PC_READY`, then arrange
the three GUI windows for the intended screenshot.

If an RViz window initially lacks a display, set its fixed frame to `map` and
select namespaced topics for that robot. Expected content includes the map,
robot model, lidar returns, global/local costmaps, and the planned path.

### 4. Ubuntu PC, second terminal: execute the task

```bash
cd ~/ROS2-Monitor-Infra
eval/e5/manual/pc.sh mission run_gui_20260715_120000
```

The mission sends both robots through the central room at the same time and
then sends them back. Leave the PC start terminal running while the mission
terminal reports both legs. A successful completion ends with
`E5_PC_MISSION_DONE`.

The most useful screenshot windows are approximately 10--20 seconds into leg
1 and 8--15 seconds into leg 2. Capture Gazebo and both RViz views together;
also capture the Mac `runner.log` when the `fleet_separation` verdict changes
to `false`. Do not pause Gazebo for a long time, because mission cancellation
uses wall time.

## Expected observations

- Gazebo initially shows robot1 at the west side near `(-2.0, -0.5)` and
  robot2 at the east side near `(2.5, 0.0)`, facing one another.
- In leg 1 they travel to the opposite ends of the map; in leg 2 they return.
  Both crossings occur in or near the central room. The planners should avoid
  sustained physical collision while the inter-robot distance briefly falls
  below the experiment's `1.0 m` property threshold.
- Each RViz window is namespaced to one robot. It should show that robot's
  localization, path, lidar, and costmaps. The modified simulation model makes
  the sibling robot visible to lidar, so it should also affect the local
  obstacle/costmap view during a crossing.
- The Pi continuously records seven ROS 2 sources: two command velocities, two
  AMCL poses, two odometry streams, and the DDS probe. Records are published
  over MQTT with QoS 1.
- The Mac receives the same stream as the Pi reference verifier. Its
  separation output should normally show two `false` intervals followed by a
  return to `true`, one interval per crossing. Exact speed-verdict counts and
  minimum separation vary with the generated trajectories and should not be
  treated as fixed GUI-run targets.

Status can be checked at any time from a spare terminal:

```bash
eval/e5/manual/pi.sh status  run_gui_20260715_120000   # on Pi
eval/e5/manual/mac.sh status run_gui_20260715_120000   # on Mac
eval/e5/manual/pc.sh status  run_gui_20260715_120000   # on PC
```

## Ordered shutdown

After the mission has completed, stop producers before consumers so queued
MQTT messages can drain. Run these commands in order and wait for the named
confirmation before advancing:

1. On the PC, stop the DDS publisher:

   ```bash
   eval/e5/manual/pc.sh stop-probe run_gui_20260715_120000
   ```

   Wait for `E5_PC_PROBE_STOPPED` in the PC start terminal or `probe_stopped`
   in PC status.

2. On the Pi, stop collection:

   ```bash
   eval/e5/manual/pi.sh stop-monitor run_gui_20260715_120000
   ```

   Wait until Pi status lists `monitor_stopped`.

3. On the Mac, stop the remote verdict runner:

   ```bash
   eval/e5/manual/mac.sh stop run_gui_20260715_120000
   ```

   Its start terminal should end with `E5_MAC_DONE`.

4. On the Pi, stop the reference runner and broker:

   ```bash
   eval/e5/manual/pi.sh stop-all run_gui_20260715_120000
   ```

   Its start terminal should end with `E5_PI_DONE`.

5. On the PC, close simulation and visualization:

   ```bash
   eval/e5/manual/pc.sh stop run_gui_20260715_120000
   ```

   Its start terminal should end with `E5_PC_DONE`.

If a PC GUI process is interrupted unexpectedly, `pc.sh` runs the targeted E4
cleanup automatically. The normal manual run leaves each machine's artifacts
under the same relative `eval/e5/results/<RUN_ID>/` path; it does not retrieve
or analyze them automatically.

## Thesis screenshot placeholder

The thesis already reserves
`Thesis/figures/evaluation/e5_headless_sessions.png`. For the optional GUI
illustration, use that location for a collage containing Gazebo/RViz, the Pi
monitor log, and a simultaneous Mac separation verdict, or update the figure
caption and filename together if the existing headless-session figure is kept.
