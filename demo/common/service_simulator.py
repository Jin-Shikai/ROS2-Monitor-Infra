#!/usr/bin/env python3
"""Small ROS2 service demo for dashboard discovery and monitoring.

The node exposes one Trigger service and calls it periodically so service
introspection events can be observed by the monitor.
"""

from __future__ import annotations

import sys

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_srvs.srv import Trigger


CALL_PERIOD_SECONDS = 3.0


class DemoServiceRobot(Node):
    def __init__(self) -> None:
        super().__init__("demo_service_robot")
        self.call_count = 0
        self.service = self.create_service(Trigger, "reset_pose", self.handle_reset)
        self.client = self.create_client(Trigger, "reset_pose")
        self._enable_service_introspection()
        self.create_timer(CALL_PERIOD_SECONDS, self.call_reset)
        self.get_logger().info(
            "Service demo started; exposes /reset_pose and calls it every "
            f"{CALL_PERIOD_SECONDS:g}s"
        )

    def _enable_service_introspection(self) -> None:
        try:
            from rclpy.service_introspection import ServiceIntrospectionState

            qos = QoSProfile(
                depth=50,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            self.service.configure_introspection(
                self.get_clock(),
                qos,
                ServiceIntrospectionState.CONTENTS,
            )
            self.get_logger().info(
                "PUBLISH: /reset_pose service introspection enabled"
            )
        except Exception as ex:  # pragma: no cover - depends on ROS distro support.
            self.get_logger().warning(
                "Service introspection could not be enabled; discovery still works "
                f"but monitor records may stay empty: {ex}"
            )

    def handle_reset(
        self,
        request: Trigger.Request,
        response: Trigger.Response,
    ) -> Trigger.Response:
        _ = request
        self.call_count += 1
        response.success = True
        response.message = f"reset accepted #{self.call_count}"
        self.get_logger().info("SERVICE: /reset_pose response success = true")
        return response

    def call_reset(self) -> None:
        if not self.client.service_is_ready():
            self.get_logger().info("SERVICE: waiting for /reset_pose")
            return
        self.client.call_async(Trigger.Request())
        self.get_logger().info("CALL: /reset_pose")


def main() -> None:
    rclpy.init(args=sys.argv)
    node = DemoServiceRobot()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
