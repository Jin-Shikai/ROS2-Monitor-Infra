#!/usr/bin/env python3

from __future__ import annotations

import sys

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.service_introspection import ServiceIntrospectionState
from std_srvs.srv import Trigger


class ResetPoseRobot(Node):
    def __init__(self) -> None:
        super().__init__("reset_pose_robot")
        self.x = 0.0
        self.reset_count = 0
        self.odom = self.create_publisher(Odometry, "odom", 10)
        self.service = self.create_service(Trigger, "reset_pose", self.reset_pose)
        qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.service.configure_introspection(
            self.get_clock(), qos, ServiceIntrospectionState.CONTENTS
        )
        self.client = self.create_client(Trigger, "reset_pose")
        self.create_timer(0.2, self.publish_odom)
        self.create_timer(3.0, self.call_reset)
        self.get_logger().info("reset_pose demo: odd calls reset odom, even calls do not")

    def publish_odom(self) -> None:
        self.x += 0.02
        msg = Odometry()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "odom"
        msg.child_frame_id = "base_link"
        msg.pose.pose.position.x = self.x
        msg.pose.pose.orientation.w = 1.0
        self.odom.publish(msg)

    def reset_pose(self, request, response):
        self.reset_count += 1
        if self.reset_count % 2 == 1:
            self.x = 0.0
            self.get_logger().info("SERVICE: /reset_pose success, pose reset")
        else:
            self.get_logger().info("SERVICE: /reset_pose success, pose not reset")
        response.success = True
        response.message = f"reset #{self.reset_count}"
        return response

    def call_reset(self) -> None:
        if self.client.service_is_ready():
            self.client.call_async(Trigger.Request())


def main() -> None:
    rclpy.init(args=sys.argv)
    node = ResetPoseRobot()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
