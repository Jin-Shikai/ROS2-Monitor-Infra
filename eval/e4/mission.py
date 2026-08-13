#!/usr/bin/env python3
"""E4 mission driver: two Nav2 robots on deliberately crossing patrol routes.

robot1 starts at the west end of the corridor world, robot2 at the east end.
Leg 1 sends both robots beyond each other's start position at the same time,
forcing a head-on pass inside the central room without letting the first
arrival occupy the other robot's start; leg 2 sends them back, producing a
second pass. Every goal event is written to a wall-clock
timestamped JSON log that serves as ground truth for the fleet-separation
property check (each leg must contain at least one separation violation).

AMCL initial poses are published by run.sh during bringup (the shared Nav2
params file cannot carry two different poses). They are also assigned to each
BasicNavigator before the readiness checks. This prevents any later pose
republish from falling back to the library's default (0, 0), which would
overwrite the robot-specific pose.

The mission deliberately does not call waitUntilNav2Active(). In this
composed multi-robot setup its lifecycle get_state service can discover the
server but lose the response in Fast DDS, blocking forever even though every
Nav2 node is active. Readiness here is instead the two conditions the mission
actually needs: an AMCL pose has been received and NavigateToPose is ready.

    python3 eval/e4/mission.py --log mission_log.json [--cancel-after 120]

With --loop the two crossing legs repeat endlessly (the WebUI application
mode); the mission log is rewritten after every leg and the loop ends on
SIGINT/SIGTERM, cancelling any in-flight goals.
"""

from __future__ import annotations

import argparse
import json
import math
import signal
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

ROBOT1_START = (-2.0, -0.5, 0.0)
ROBOT2_START = (2.5, 0.0, math.pi)

# Deliberately extend leg 1 beyond the opposite spawn positions. With goals
# exactly at the other robot's start, the faster robot can stop on the slower
# robot's only exit and deadlock the mission. These points are in the same end
# rooms with 0.77 m / 1.20 m static-map clearance, respectively.
WEST_GOAL = (-3.0, -0.5, 0.0)
EAST_GOAL = (3.0, 0.0, math.pi)


def make_pose(nav: BasicNavigator, x: float, y: float, yaw: float) -> PoseStamped:
    pose = PoseStamped()
    pose.header.frame_id = "map"
    pose.header.stamp = nav.get_clock().now().to_msg()
    pose.pose.position.x = x
    pose.pose.position.y = y
    pose.pose.orientation.z = math.sin(yaw / 2)
    pose.pose.orientation.w = math.cos(yaw / 2)
    return pose


def wait_until_ready(
    robot: str,
    nav: BasicNavigator,
    timeout_sec: float,
) -> None:
    """Wait for localization data and the navigation action without services."""
    deadline = time.monotonic() + timeout_sec
    next_pose_publish = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        # Processes the transient-local AMCL pose callback. Action discovery
        # itself is handled by DDS and does not require lifecycle get_state.
        rclpy.spin_once(nav, timeout_sec=0.2)
        action_ready = nav.nav_to_pose_client.server_is_ready()
        if nav.initial_pose_received and action_ready:
            print(f"{robot} ready: AMCL pose + NavigateToPose action", flush=True)
            return
        if time.monotonic() >= next_pose_publish:
            # Republish the already assigned robot-specific pose without
            # resetting initial_pose_received (setInitialPose would reset it).
            nav._setInitialPose()
            next_pose_publish = time.monotonic() + 2.0
    raise TimeoutError(
        f"{robot} not ready after {timeout_sec:.1f}s "
        f"(amcl_pose={nav.initial_pose_received}, "
        f"navigate_to_pose={nav.nav_to_pose_client.server_is_ready()})"
    )


def run_leg(
    leg: str,
    goals: dict[str, tuple[float, float, float]],
    navs: dict[str, BasicNavigator],
    events: list,
    cancel_after: float,
) -> dict[str, str]:
    sent = time.time()
    for robot, goal in goals.items():
        events.append(
            {"type": "goal_sent", "leg": leg, "robot": robot, "t": time.time(),
             "pose": goal}
        )
        navs[robot].goToPose(make_pose(navs[robot], *goal))
    pending = dict(navs)
    canceled: set[str] = set()
    results: dict[str, str] = {}
    while pending:
        for robot, nav in list(pending.items()):
            if nav.isTaskComplete():
                result = nav.getResult()
                results[robot] = RESULT_NAMES.get(result, str(result))
                events.append(
                    {
                        "type": "goal_result",
                        "leg": leg,
                        "robot": robot,
                        "t": time.time(),
                        "duration_sec": time.time() - sent,
                        "result": results[robot],
                        "canceled_by_mission": robot in canceled,
                    }
                )
                print(
                    f"leg {leg} {robot}: {results[robot]} "
                    f"in {time.time() - sent:.1f}s",
                    flush=True,
                )
                del pending[robot]
            elif robot not in canceled and time.time() - sent > cancel_after:
                nav.cancelTask()
                canceled.add(robot)
        time.sleep(0.2)
    return results


def recover_robots(
    navs: dict[str, BasicNavigator],
    events: list,
    cancel_after: float,
) -> None:
    """Untangle a head-on deadlock by moving one robot at a time.

    After a canceled leg the robots usually stand nose-to-nose in the
    corridor; re-sending simultaneous goals just reproduces the standoff.
    Returning them to their distinct start poses sequentially lets the first
    robot back away while the other keeps still."""
    starts = {"robot1": ROBOT1_START, "robot2": ROBOT2_START}
    for robot, pose in starts.items():
        nav = navs[robot]
        print(f"recovery: sending {robot} back to its start pose", flush=True)
        events.append({"type": "recovery_started", "robot": robot, "t": time.time()})
        nav.goToPose(make_pose(nav, *pose))
        deadline = time.monotonic() + cancel_after
        canceled = False
        while not nav.isTaskComplete():
            if not canceled and time.monotonic() > deadline:
                nav.cancelTask()
                canceled = True
            time.sleep(0.2)
        result = RESULT_NAMES.get(nav.getResult(), "UNKNOWN")
        events.append(
            {"type": "recovery_result", "robot": robot, "t": time.time(),
             "result": result}
        )
        print(f"recovery {robot}: {result}", flush=True)


def write_log(path: str, events: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"events": events}, f, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True)
    parser.add_argument("--cancel-after", type=float, default=120.0)
    parser.add_argument("--ready-timeout", type=float, default=30.0)
    parser.add_argument(
        "--loop",
        action="store_true",
        help="repeat the two crossing legs until interrupted",
    )
    args = parser.parse_args()

    # A plain SIGTERM (WebUI stop, kill) should take the same clean path as
    # Ctrl-C: cancel in-flight goals and write the mission log.
    def raise_interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, raise_interrupt)

    rclpy.init()
    navs = {
        "robot1": BasicNavigator(namespace="robot1"),
        "robot2": BasicNavigator(namespace="robot2"),
    }
    events: list[dict] = []

    # run.sh has already published these poses to unblock Nav2 activation.
    # Store and republish the same robot-specific poses before readiness
    # checks, so BasicNavigator can never fall back to its default
    # PoseStamped at (0, 0) while waiting for an AMCL message.
    starts = {"robot1": ROBOT1_START, "robot2": ROBOT2_START}
    for robot, nav in navs.items():
        nav.setInitialPose(make_pose(nav, *starts[robot]))

    for robot, nav in navs.items():
        wait_until_ready(robot, nav, args.ready_timeout)
        events.append({"type": "nav2_active", "robot": robot, "t": time.time()})
    print("both navigators active; starting leg 1", flush=True)

    lap = 0
    try:
        while True:
            lap += 1
            # Leg 1: cross beyond the opposite starts -> head-on pass in the
            # central room.
            results = run_leg(
                "1", {"robot1": EAST_GOAL, "robot2": WEST_GOAL},
                navs, events, args.cancel_after)
            events.append({"type": "leg_done", "leg": "1", "t": time.time()})
            write_log(args.log, events)
            if set(results.values()) != {"SUCCEEDED"}:
                print("leg 1 did not fully succeed; recovering", flush=True)
                recover_robots(navs, events, args.cancel_after)
                write_log(args.log, events)
                if not args.loop:
                    break
                time.sleep(3.0)
                continue
            time.sleep(3.0)

            # Leg 2: return to the distinct spawn positions -> second pass.
            results = run_leg(
                "2", {"robot1": ROBOT1_START, "robot2": ROBOT2_START},
                navs, events, args.cancel_after)
            events.append({"type": "leg_done", "leg": "2", "t": time.time()})
            write_log(args.log, events)
            if set(results.values()) != {"SUCCEEDED"}:
                print("leg 2 did not fully succeed; recovering", flush=True)
                recover_robots(navs, events, args.cancel_after)
                write_log(args.log, events)

            if not args.loop:
                break
            print(f"lap {lap} complete; starting the next crossing lap", flush=True)
            time.sleep(3.0)
    except KeyboardInterrupt:
        print("mission interrupted; cancelling in-flight goals", flush=True)
        events.append({"type": "interrupted", "lap": lap, "t": time.time()})
        for nav in navs.values():
            try:
                nav.cancelTask()
            except Exception:
                pass

    write_log(args.log, events)
    print(f"mission log written: {args.log}", flush=True)

    try:
        rclpy.shutdown()
    except Exception:
        pass


if __name__ == "__main__":
    main()
