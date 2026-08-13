#!/usr/bin/env python3
"""E3 mission driver: deterministic Nav2 goal sequence with obstacle events.

Drives the TB3 through three corridor goals while obstacles are spawned at
scripted times, and writes a wall-clock-timestamped JSON log that serves as
the ground truth for the goal-deadline property check:

  goal A: down the corridor, no obstacles          (unobstructed baseline)
  goal B: close the lower opening in the right partition before sending the
          return goal, forcing the upper opening    (topological detour)
  goal C: keep that barrier and close the remaining upper opening before
          sending the final goal                    (no east-west route)

The mission does not hard-code verdict polarity: the checker derives it from
each measured result and duration for the selected DEADLINE. This keeps the
correctness check valid when simulator speed changes with host load.

A goal still running `--cancel-after` seconds after being sent is canceled.
Readiness deliberately avoids lifecycle get_state services: it waits only for
an AMCL pose callback and the NavigateToPose action server, both of which are
actual prerequisites for this mission.

    python3 eval/e3/mission.py --log mission_log.json [--cancel-after 90]

With --loop the A/B/C sequence repeats until SIGINT/SIGTERM: after goal C
both barriers are removed from Gazebo, the costmaps are cleared, and the
robot navigates back to the start pose before the next run.
"""

from __future__ import annotations

import argparse
import json
import math
import signal
import subprocess
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

RESULT_NAMES = {
    TaskResult.SUCCEEDED: "SUCCEEDED",
    TaskResult.CANCELED: "CANCELED",
    TaskResult.FAILED: "FAILED",
    TaskResult.UNKNOWN: "UNKNOWN",
}

# The robot spawns at (-2.0, -0.5); AMCL's initial pose is preset to the
# same coordinates in eval/e3/nav2_params.yaml.
START = (-2.0, -0.5, 0.0)
GOAL_A = (2.5, 0.0, 0.0)
GOAL_B = (-2.0, -0.5, math.pi)
GOAL_C = (2.5, 0.0, 0.0)

# The vertical partition at x=1.4 has exactly two traversable gaps. A single
# long box bridges each complete 1.275 m gap between the static wall segments;
# unlike the former scattered boxes, these barriers change map connectivity.
# The lower barrier remains in Gazebo when the upper one is added for goal C.
RIGHT_LOWER_GATE = "0.0,e3_right_lower_gate,1.4,-1.2625,0.5,0.5,1.2,1.0"
RIGHT_UPPER_GATE = "0.0,e3_right_upper_gate,1.4,1.2625,0.5,0.5,1.2,1.0"
GATE_NAMES = ("e3_right_lower_gate", "e3_right_upper_gate")


def make_pose(nav: BasicNavigator, x: float, y: float, yaw: float) -> PoseStamped:
    pose = PoseStamped()
    pose.header.frame_id = "map"
    pose.header.stamp = nav.get_clock().now().to_msg()
    pose.pose.position.x = x
    pose.pose.position.y = y
    pose.pose.orientation.z = math.sin(yaw / 2)
    pose.pose.orientation.w = math.cos(yaw / 2)
    return pose


def wait_until_ready(nav: BasicNavigator, timeout_sec: float) -> None:
    """Wait for localization data and navigation action discovery, bounded."""
    deadline = time.monotonic() + timeout_sec
    next_pose_publish = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        rclpy.spin_once(nav, timeout_sec=0.2)
        action_ready = nav.nav_to_pose_client.server_is_ready()
        if nav.initial_pose_received and action_ready:
            return
        if time.monotonic() >= next_pose_publish:
            # Republish the explicitly assigned START pose without resetting
            # initial_pose_received (setInitialPose would reset that flag).
            nav._setInitialPose()
            next_pose_publish = time.monotonic() + 2.0
    raise TimeoutError(
        f"robot not ready after {timeout_sec:.1f}s "
        f"(amcl_pose={nav.initial_pose_received}, "
        f"navigate_to_pose={nav.nav_to_pose_client.server_is_ready()})"
    )


def spawn_barrier(name: str, obstacle: str, events: list) -> None:
    """Spawn one route-closing barrier and wait for Gazebo to confirm it."""
    events.append({"type": "obstacles_started", "scenario": name, "t": time.time()})
    subprocess.run(
        ["ros2", "run", "my_nav2_worlds", "spawn_dynamic_obstacles",
         "--obstacle", obstacle],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    events.append({"type": "obstacles_done", "scenario": name, "t": time.time()})


def remove_barriers(events: list) -> None:
    """Delete both gate models from the running Gazebo world."""
    for name in GATE_NAMES:
        subprocess.run(
            ["gz", "service", "-s", "/world/default/remove",
             "--reqtype", "gz.msgs.Entity", "--reptype", "gz.msgs.Boolean",
             "--timeout", "3000", "--req", f'name: "{name}" type: MODEL'],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    events.append({"type": "obstacles_removed", "t": time.time()})


def write_log(path: str, events: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"events": events}, f, indent=2)


def run_goal(
    nav: BasicNavigator,
    name: str,
    goal: tuple[float, float, float],
    events: list,
    cancel_after: float,
) -> None:
    sent = time.time()
    events.append({"type": "goal_sent", "goal": name, "t": sent, "pose": goal})
    print(f"nav to point ({goal[0]:.1f}, {goal[1]:.1f})", flush=True)
    nav.goToPose(make_pose(nav, *goal))
    canceled = False
    while not nav.isTaskComplete():
        if not canceled and time.time() - sent > cancel_after:
            nav.cancelTask()
            canceled = True
        time.sleep(0.2)
    result = nav.getResult()
    events.append(
        {
            "type": "goal_result",
            "goal": name,
            "t": time.time(),
            "duration_sec": time.time() - sent,
            "result": RESULT_NAMES.get(result, str(result)),
            "canceled_by_mission": canceled,
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True)
    parser.add_argument("--cancel-after", type=float, default=90.0)
    parser.add_argument("--ready-timeout", type=float, default=30.0)
    parser.add_argument(
        "--loop",
        action="store_true",
        help="repeat the A/B/C sequence until interrupted",
    )
    args = parser.parse_args()

    # A plain SIGTERM (WebUI stop, kill) should take the same clean path as
    # Ctrl-C: cancel the in-flight goal and write the mission log.
    def raise_interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, raise_interrupt)

    rclpy.init()
    nav = BasicNavigator()
    events: list[dict] = []

    # Keep BasicNavigator's internal initial pose consistent with both the
    # Gazebo spawn and nav2_params.yaml. Otherwise its readiness helper can
    # republish the library default (0, 0) during a discovery race.
    nav.setInitialPose(make_pose(nav, *START))
    wait_until_ready(nav, args.ready_timeout)
    events.append({"type": "initial_pose", "t": time.time(), "pose": START})
    events.append({"type": "nav2_active", "t": time.time()})

    run = 0
    try:
        while True:
            run += 1
            run_goal(nav, "A", GOAL_A, events, args.cancel_after)

            # Close the lower of the right partition's two gaps before
            # dispatching B. The only remaining east-west route crosses the
            # upper gap near y=+1.26.
            spawn_barrier("right_lower_gate", RIGHT_LOWER_GATE, events)
            run_goal(nav, "B", GOAL_B, events, args.cancel_after)

            # Keep the lower barrier and close the upper gap too. This
            # disconnects the east and west halves; C reveals whether Nav2
            # fails, waits, or is canceled.
            spawn_barrier("right_upper_gate", RIGHT_UPPER_GATE, events)
            run_goal(nav, "C", GOAL_C, events, args.cancel_after)

            events.append({"type": "run_done", "run": run, "t": time.time()})
            write_log(args.log, events)
            if not args.loop:
                break

            remove_barriers(events)
            nav.clearAllCostmaps()
            run_goal(nav, "home", START, events, args.cancel_after)
            write_log(args.log, events)
            time.sleep(3.0)
    except KeyboardInterrupt:
        events.append({"type": "interrupted", "run": run, "t": time.time()})
        try:
            nav.cancelTask()
        except Exception:
            pass

    write_log(args.log, events)
    rclpy.shutdown()


if __name__ == "__main__":
    main()
