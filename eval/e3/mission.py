#!/usr/bin/env python3
"""E3 mission driver: deterministic Nav2 goal sequence with obstacle events.

Drives the TB3 through three corridor goals while obstacles are spawned at
scripted times, and writes a wall-clock-timestamped JSON log that serves as
the ground truth for the goal-deadline property check:

  goal A: down the corridor, no obstacles          (expected: within deadline)
  goal B: back through the obstacle zone while the `three_boxes` preset
          spawns boxes into the robot's path        (expected: slowed)
  goal C: down the corridor again after the `temporary_wall` preset has
          blocked it                               (expected: late or aborted)

A goal still running `--cancel-after` seconds after being sent is canceled
so the mission always terminates.

    python3 eval/e3/mission.py --log mission_log.json [--cancel-after 90]
"""

from __future__ import annotations

import argparse
import json
import math
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
GOAL_A = (2.5, 0.0, 0.0)
GOAL_B = (-2.0, -0.5, math.pi)
GOAL_C = (2.5, 0.0, 0.0)


def make_pose(nav: BasicNavigator, x: float, y: float, yaw: float) -> PoseStamped:
    pose = PoseStamped()
    pose.header.frame_id = "map"
    pose.header.stamp = nav.get_clock().now().to_msg()
    pose.pose.position.x = x
    pose.pose.position.y = y
    pose.pose.orientation.z = math.sin(yaw / 2)
    pose.pose.orientation.w = math.cos(yaw / 2)
    return pose


def spawn_obstacles(scenario: str, events: list, wait: bool) -> subprocess.Popen:
    events.append({"type": "obstacles_started", "scenario": scenario, "t": time.time()})
    proc = subprocess.Popen(
        ["ros2", "run", "my_nav2_worlds", "spawn_dynamic_obstacles",
         "--scenario", scenario]
    )
    if wait:
        proc.wait()
        events.append({"type": "obstacles_done", "scenario": scenario, "t": time.time()})
    return proc


def run_goal(
    nav: BasicNavigator,
    name: str,
    goal: tuple[float, float, float],
    events: list,
    cancel_after: float,
) -> None:
    sent = time.time()
    events.append({"type": "goal_sent", "goal": name, "t": sent, "pose": goal})
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
    print(f"{name}: {RESULT_NAMES.get(result)} in {time.time() - sent:.1f}s", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True)
    parser.add_argument("--cancel-after", type=float, default=90.0)
    args = parser.parse_args()

    rclpy.init()
    nav = BasicNavigator()
    events: list[dict] = []

    # AMCL's initial pose is set via parameters (eval/e3/nav2_params.yaml),
    # so waiting for the stack to become active is sufficient here.
    nav.waitUntilNav2Active()
    events.append({"type": "nav2_active", "t": time.time()})
    print("nav2 active; starting mission", flush=True)

    run_goal(nav, "A", GOAL_A, events, args.cancel_after)

    # Boxes appear in the corridor while the robot drives back through it.
    boxes = spawn_obstacles("three_boxes", events, wait=False)
    run_goal(nav, "B", GOAL_B, events, args.cancel_after)
    boxes.wait()
    events.append({"type": "obstacles_done", "scenario": "three_boxes", "t": time.time()})

    # Block the corridor, then try to cross it again.
    spawn_obstacles("temporary_wall", events, wait=True)
    run_goal(nav, "C", GOAL_C, events, args.cancel_after)

    with open(args.log, "w", encoding="utf-8") as f:
        json.dump({"events": events}, f, indent=2)
    print(f"mission log written: {args.log}", flush=True)

    rclpy.shutdown()


if __name__ == "__main__":
    main()
