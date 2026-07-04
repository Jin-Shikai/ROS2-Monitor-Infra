#!/usr/bin/env python3
"""Small ROS2 action demo for dashboard discovery and monitoring.

The node exposes one Fibonacci action and sends itself goals periodically so
feedback/status hidden topics can be observed by the monitor.
"""

from __future__ import annotations

import sys
import time

import rclpy
from example_interfaces.action import Fibonacci
from rclpy.action import ActionClient, ActionServer
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node


GOAL_PERIOD_SECONDS = 5.0
GOAL_ORDER = 6


class DemoActionRobot(Node):
    def __init__(self) -> None:
        super().__init__("demo_action_robot")
        self.callback_group = ReentrantCallbackGroup()
        self.goal_active = False
        self.action_server = ActionServer(
            self,
            Fibonacci,
            "demo_fibonacci",
            execute_callback=self.execute_goal,
            callback_group=self.callback_group,
        )
        self.action_client = ActionClient(
            self,
            Fibonacci,
            "demo_fibonacci",
            callback_group=self.callback_group,
        )
        self.create_timer(
            GOAL_PERIOD_SECONDS,
            self.send_goal,
            callback_group=self.callback_group,
        )
        self.get_logger().info(
            "Action demo started; exposes /demo_fibonacci and sends a goal every "
            f"{GOAL_PERIOD_SECONDS:g}s"
        )

    def send_goal(self) -> None:
        if self.goal_active:
            return
        if not self.action_client.server_is_ready():
            self.get_logger().info("ACTION: waiting for /demo_fibonacci")
            return
        goal = Fibonacci.Goal()
        goal.order = GOAL_ORDER
        self.goal_active = True
        self.get_logger().info(f"GOAL: /demo_fibonacci order = {GOAL_ORDER}")
        future = self.action_client.send_goal_async(
            goal,
            feedback_callback=self.on_feedback,
        )
        future.add_done_callback(self.on_goal_response)

    def on_goal_response(self, future) -> None:
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.goal_active = False
            self.get_logger().warning("ACTION: /demo_fibonacci goal rejected")
            return
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.on_result)

    def on_feedback(self, feedback_msg) -> None:
        sequence = list(feedback_msg.feedback.sequence)
        self.get_logger().info(f"FEEDBACK: /demo_fibonacci sequence = {sequence}")

    def on_result(self, future) -> None:
        result = future.result().result
        self.goal_active = False
        self.get_logger().info(f"RESULT: /demo_fibonacci sequence = {list(result.sequence)}")

    def execute_goal(self, goal_handle) -> Fibonacci.Result:
        sequence = [0, 1]
        for _ in range(1, goal_handle.request.order):
            sequence.append(sequence[-1] + sequence[-2])
            feedback = Fibonacci.Feedback()
            feedback.sequence = sequence
            goal_handle.publish_feedback(feedback)
            time.sleep(0.3)
        goal_handle.succeed()
        result = Fibonacci.Result()
        result.sequence = sequence
        return result


def main() -> None:
    rclpy.init(args=sys.argv)
    node = DemoActionRobot()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
