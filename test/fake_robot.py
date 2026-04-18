#!/usr/bin/env python3
"""Fake robot node that publishes diverse topics, hosts a service, and runs an action server.

Usage (native):
    source /opt/ros/kilted/setup.bash
    python3 test/fake_robot.py

Publishes:
    /odom          nav_msgs/msg/Odometry        @ 10 Hz  (simulated circular motion)
    /scan          sensor_msgs/msg/LaserScan    @ 5 Hz   (simulated 360° LIDAR)
    /cmd_vel       geometry_msgs/msg/Twist      @ 2 Hz   (velocity command)
    /chatter       std_msgs/msg/String          @ 1 Hz   (status text)

Service server:
    /set_bool      std_srvs/srv/SetBool         (toggles an internal flag)

Action server:
    /fibonacci     example_interfaces/action/Fibonacci  (computes Fibonacci sequence)
"""

import math
import random
import time

import rclpy
from rclpy.action import ActionServer
from rclpy.node import Node
from rclpy.qos import qos_profile_system_default
from rclpy.service_introspection import ServiceIntrospectionState

from std_msgs.msg import String
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from std_srvs.srv import SetBool
from example_interfaces.action import Fibonacci
from builtin_interfaces.msg import Time


class FakeRobot(Node):
    def __init__(self):
        super().__init__("fake_robot")
        self._start_time = time.time()
        self._enabled = True  # toggled by SetBool service

        # --- Publishers ---
        self.pub_odom = self.create_publisher(Odometry, "/odom", 10)
        self.pub_scan = self.create_publisher(LaserScan, "/scan", 10)
        self.pub_cmd = self.create_publisher(Twist, "/cmd_vel", 10)
        self.pub_chat = self.create_publisher(String, "/chatter", 10)

        # --- Timers ---
        self.create_timer(0.1, self._publish_odom)    # 10 Hz
        self.create_timer(0.2, self._publish_scan)     # 5 Hz
        self.create_timer(0.5, self._publish_cmd_vel)  # 2 Hz
        self.create_timer(1.0, self._publish_chatter)  # 1 Hz

        # --- Service server (with introspection enabled) ---
        self.srv = self.create_service(
            SetBool, "/set_bool", self._handle_set_bool,
        )
        # Enable service introspection so events appear on /set_bool/_service_event
        self.srv.configure_introspection(
            self.get_clock(),
            qos_profile_system_default,
            ServiceIntrospectionState.CONTENTS,
        )

        # --- Action server ---
        self._action_server = ActionServer(
            self, Fibonacci, "/fibonacci", self._execute_fibonacci
        )

        self.get_logger().info("FakeRobot started — publishing topics, serving /set_bool, action /fibonacci")

    # ------------------------------------------------------------------ #
    # Topic publishers
    # ------------------------------------------------------------------ #

    def _now_stamp(self) -> Time:
        t = self.get_clock().now().to_msg()
        return t

    def _publish_odom(self):
        msg = Odometry()
        msg.header.stamp = self._now_stamp()
        msg.header.frame_id = "odom"
        msg.child_frame_id = "base_link"
        # Simulate circular motion
        elapsed = time.time() - self._start_time
        radius = 2.0
        msg.pose.pose.position.x = radius * math.cos(0.2 * elapsed)
        msg.pose.pose.position.y = radius * math.sin(0.2 * elapsed)
        msg.pose.pose.position.z = 0.0
        msg.pose.pose.orientation.w = math.cos(0.1 * elapsed)
        msg.pose.pose.orientation.z = math.sin(0.1 * elapsed)
        msg.twist.twist.linear.x = 0.4
        msg.twist.twist.angular.z = 0.2
        self.pub_odom.publish(msg)

    def _publish_scan(self):
        msg = LaserScan()
        msg.header.stamp = self._now_stamp()
        msg.header.frame_id = "base_scan"
        msg.angle_min = -math.pi
        msg.angle_max = math.pi
        msg.angle_increment = math.pi / 180.0  # 1 degree resolution
        msg.time_increment = 0.0
        msg.scan_time = 0.2
        msg.range_min = 0.12
        msg.range_max = 3.5
        num_readings = int((msg.angle_max - msg.angle_min) / msg.angle_increment)
        # Simulate a room with some obstacles
        msg.ranges = [
            max(msg.range_min, min(msg.range_max, 2.0 + 0.5 * math.sin(i * 0.1) + random.uniform(-0.05, 0.05)))
            for i in range(num_readings)
        ]
        self.pub_scan.publish(msg)

    def _publish_cmd_vel(self):
        msg = Twist()
        if self._enabled:
            msg.linear.x = 0.26
            msg.angular.z = 0.1 * math.sin(time.time())
        # else: zero twist (robot stopped)
        self.pub_cmd.publish(msg)

    def _publish_chatter(self):
        msg = String()
        elapsed = int(time.time() - self._start_time)
        status = "running" if self._enabled else "paused"
        msg.data = f"[{elapsed}s] fake_robot status: {status}"
        self.pub_chat.publish(msg)

    # ------------------------------------------------------------------ #
    # Service handler
    # ------------------------------------------------------------------ #

    def _handle_set_bool(self, request, response):
        self._enabled = request.data
        response.success = True
        response.message = f"Robot {'enabled' if self._enabled else 'disabled'}"
        self.get_logger().info(f"SetBool called: data={request.data} -> {response.message}")
        return response

    # ------------------------------------------------------------------ #
    # Action handler
    # ------------------------------------------------------------------ #

    def _execute_fibonacci(self, goal_handle):
        self.get_logger().info(f"Fibonacci goal received: order={goal_handle.request.order}")
        feedback_msg = Fibonacci.Feedback()
        feedback_msg.sequence = [0, 1]

        for i in range(1, goal_handle.request.order):
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                self.get_logger().info("Fibonacci canceled")
                return Fibonacci.Result()

            feedback_msg.sequence.append(
                feedback_msg.sequence[i] + feedback_msg.sequence[i - 1]
            )
            goal_handle.publish_feedback(feedback_msg)
            time.sleep(0.5)  # simulate computation time

        goal_handle.succeed()
        result = Fibonacci.Result()
        result.sequence = feedback_msg.sequence
        self.get_logger().info(f"Fibonacci result: {list(result.sequence)}")
        return result


def main():
    rclpy.init()
    node = FakeRobot()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
