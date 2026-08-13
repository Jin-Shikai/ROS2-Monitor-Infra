# E3 through the WebUI (interactive three-goal mission)

This playbook re-creates the thesis E3 experiment (one TurtleBot3/Nav2 robot
in the custom corridor world, deterministic three-goal mission with scripted
route-closing obstacles) interactively in the WebUI. Two properties are
checked online, as in the thesis: the 0.2 m/s commanded-speed limit and the
35-second navigation-goal deadline. The runtimes mirror the thesis process
split: collection (`monitor_node`) and evaluation (`node_runner`) run as
separate host processes linked over MQTT.

Expected outcomes, matching the thesis: goal A succeeds within the deadline
(positive verdict), goal B is forced through the upper route and exceeds the
35-second deadline while still active (negative verdict, detected in flight),
goal C is aborted after both openings are closed (negative verdict).

In Local Mode everything runs **natively** on this machine: the ROS
application and the generated monitoring runtimes are host processes.

## 1. Start the WebUI service

From a terminal with ROS sourced (system Python, not the `.venv`):

```bash
cd ~/ROS2-Monitor-Infra
deactivate 2>/dev/null; set +u; source /opt/ros/kilted/setup.bash; source ~/ros2_ws/install/setup.bash; set -u
python3 webui/server.py
```

Open <http://127.0.0.1:8765>. Stay in **Local Mode**.

The `deactivate` matters: IDE terminals (VS Code) often auto-activate the
uv `.venv`, whose interpreter lacks `numpy`/`rclpy`. The server spawns the
generated runtimes with its **own** interpreter and passes its PATH to the
application, so a venv-started server breaks both. `run_app.sh` detects the
leaked venv and refuses to run with a clear message; the runtimes cannot,
so start the server correctly. `command -v python3` must print
`/usr/bin/python3` before launching the server.

## 2. Create the hosts

Press **New Host** twice and rename via *Host id*:

- `e3mon` — collection: the ROS 2 sources and the monitor.
- `e3run` — evaluation: the converters and the verdict services.

Because the dataflow crosses a host boundary, an MQTT broker block appears
once the blocks are connected. The default broker `127.0.0.1:1883` is fine:
the WebUI reuses a broker already listening there, or starts its own
mosquitto.

## 3. Declare the observed sources

With `e3mon` selected, add the two sources by hand (the simulation does not
need to be running; **Scan graph** while the app runs is the alternative):

- topic `/cmd_vel`, interface `geometry_msgs/msg/TwistStamped`
- action `/navigate_to_pose`, interface `nav2_msgs/action/NavigateToPose`
  (feedback and status phases are collected by default)

The headless E3 additionally records rate-limited `/odom` fields; neither
property needs them, and the WebUI declares raw sources only, so `/odom` is
omitted here.

## 4. Build the runtimes

Monitor on `e3mon`:

1. **+ Monitor** → id `monitor_e3`. Select the two source blocks (click,
   then shift-click), shift-click the monitor block last, press **Connect**.

Converters and verdicts on `e3run`:

2. **+ Converter** → `cmd_speed`: manifest *Command Speed Converter*, set
   `speed_path` to `twist.linear.x` (the `/cmd_vel` interface is
   TwistStamped). Connect the `/cmd_vel` source → `cmd_speed`.
3. **+ Converter** → `nav_goal`: manifest *Nav Goal Deadline Converter*
   (defaults: action `/navigate_to_pose`, deadline 35 s). Connect the
   `/navigate_to_pose` action source → `nav_goal`.
4. **+ Verdict** → `speed_check`: *Threshold Verdict*, threshold `0.2`.
   Connect `cmd_speed` → `speed_check`.
5. **+ Verdict** → `nav_deadline_check`: *Nav Goal Deadline Verdict*
   (defaults). Connect `nav_goal` → `nav_deadline_check`.

## 5. Start the runtimes first

Click empty playground space (nothing selected) and press **Start**. This
generates `generated/showcase/e3mon.yaml` and `e3run.yaml` and launches the
`monitor_node` (collection), the `node_runner` (evaluation), and the broker.
They idle until the application produces data — starting them before the
mission guarantees goal A is captured from its first record.

## 6. Start the ROS application and observe

1. Select the `e3mon` host. In the *ROS application* section set the start
   command to:

   ```
   eval/e3/run_app.sh
   ```

2. With the host still selected, press **Start**. A Gazebo window and an
   RViz window open; bringup takes 1–2 minutes (watch the *Live log* — it
   announces when Nav2 is active and when the mission starts). Prefix the
   command with `HEADLESS=True` or `USE_RVIZ=False` to disable windows.
3. The three-goal mission then runs on its own (about 3–5 minutes):
   - **Goal A** crosses through the lower opening and succeeds in ~25 s →
     `nav_goal_deadline` verdict `true`.
   - A red barrier closes the lower opening; **goal B** is forced through
     the upper route. When 35 s pass with the goal still active, the
     in-flight `nav_goal_deadline: false` verdict appears in the Live log —
     the robot still completes the goal late (~70 s).
   - A second barrier closes the upper opening; **goal C** cannot reach the
     right side and Nav2 aborts → final `nav_goal_deadline: false`.
   - Throughout, `speed_check` flips to `false` whenever the commanded
     speed exceeds 0.2 m/s and recovers when the robot slows.
4. After goal C the mission resets itself: both barriers are deleted from
   Gazebo, the costmaps are cleared, and the robot navigates back to the
   start pose (this homing goal is monitored too, so one extra positive
   `nav_goal_deadline` verdict appears per cycle). A/B/C then repeat until
   **Stop** is pressed.

Verdict files accumulate under `output/showcase/e3run/verdicts_*.jsonl`;
the mission log and Nav2 log land in `eval/e3/results/webui_<timestamp>/`.

## 7. Stop everything

Nothing selected → **Stop**: the runtimes stop first so in-flight records
drain, then the application is interrupted — Gazebo/RViz close and
`eval/e3/cleanup.sh` purges any leftovers. If a session ever hangs, run
`eval/e3/cleanup.sh` manually.

## Troubleshooting

- **Bringup stalls, `nav2.log` shows `X Error ... GLX` or RViz `Failed to
  create an OpenGL context`**: OpenGL is broken system-wide, typically after
  an NVIDIA driver update left the old kernel module loaded. Reboot and
  retry (the Gazebo server needs OpenGL for the GPU lidar even without a
  window).
- **Goal B succeeds within 35 s** (simulation speed varies with host load):
  the deadline is the *Nav Goal Deadline Converter*'s `deadline_sec` param —
  lower it to force the thesis outcome, or accept the positive verdict.
- **A scan shows no `/navigate_to_pose`**: the action server only exists
  while Nav2 is up; scan again after bringup, or declare the source
  manually as in step 3.

## Notes

- The single-host variant (everything on one host, no broker block) also
  works, like the E4 playbook's layout; the two-host split above matches
  the thesis E3 deployment (collection and evaluation over MQTT).
- The headless reference experiment with offline oracle checks remains
  `eval/e3/run.sh`; this playbook is for interactive demonstration and
  screen recording.
