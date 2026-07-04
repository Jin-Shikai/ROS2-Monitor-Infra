#!/usr/bin/env python3
"""Small ROS2 publisher for self-contained deployment demos.

Each named scenario has fixed, visible input values and changes phase every
three seconds. ROS names and namespaces are set with normal ROS remapping
arguments, for example:

    python3 robot_simulator.py speed-limit-cycle \
      --ros-args -r __node:=robot1 -r __ns:=/robot1
"""

from __future__ import annotations

import argparse
import sys

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node


PHASE_SECONDS = 3.0
SCENARIOS = (
    "speed-limit-cycle",
    "cmd-velocity-cycle",
    "stationary-origin",
    "minimum-distance-cycle",
)


class DemoRobot(Node):
    def __init__(self, scenario: str):
        super().__init__("demo_robot")
        self.scenario = scenario
        self.started_at = self.get_clock().now()
        self.last_phase = -1
        self.odom_publisher = self.create_publisher(Odometry, "odom", 10)
        self.cmd_publisher = self.create_publisher(Twist, "cmd_vel", 10)
        self.create_timer(0.2, self.publish_state)
        self.get_logger().info(
            f"Scenario '{scenario}' started; phase changes every {PHASE_SECONDS:g}s"
        )

    def publish_state(self) -> None:
        elapsed = (self.get_clock().now() - self.started_at).nanoseconds / 1e9
        phase = int(elapsed / PHASE_SECONDS) % 2
        odom_speed, cmd_speed, position_x, description = scenario_state(
            self.scenario, phase
        )
        if phase != self.last_phase:
            self.last_phase = phase
            self.get_logger().info(description)

        odom = Odometry()
        odom.header.stamp = self.get_clock().now().to_msg()
        odom.header.frame_id = "odom"
        odom.child_frame_id = "base_link"
        odom.pose.pose.position.x = position_x
        odom.pose.pose.orientation.w = 1.0
        odom.twist.twist.linear.x = odom_speed
        self.odom_publisher.publish(odom)

        cmd = Twist()
        cmd.linear.x = cmd_speed
        self.cmd_publisher.publish(cmd)


def scenario_state(scenario: str, phase: int) -> tuple[float, float, float, str]:
    if scenario == "speed-limit-cycle":
        speed = 0.4 if phase == 0 else 0.2
        return speed, 0.2, 0.0, f"PUBLISH: /odom speed = {speed:.1f} m/s"

    if scenario == "cmd-velocity-cycle":
        speed = 1.85 if phase == 0 else 0.2
        return 0.2, speed, 0.0, f"PUBLISH: /cmd_vel linear.x = {speed:.2f} m/s"

    if scenario == "stationary-origin":
        return 0.0, 0.0, 0.0, "PUBLISH: robot x = 0.0 m"

    distance = 0.5 if phase == 0 else 1.5
    return 0.0, 0.0, distance, f"PUBLISH: robot x = {distance:.1f} m"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=SCENARIOS)
    args, ros_args = parser.parse_known_args()
    rclpy.init(args=[sys.argv[0], *ros_args])
    node = DemoRobot(args.scenario)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
