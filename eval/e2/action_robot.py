#!/usr/bin/env python3
"""Fibonacci action fixture for E2 observable-breadth monitoring.

One node hosts an `example_interfaces/action/Fibonacci` action server and a
client that sends a goal of fixed order every `--period` seconds. The server
publishes one feedback message per computed element (order - 1 messages per
goal) and succeeds every goal, so the monitor-side ground truth per goal is:
order - 1 feedback records and one SUCCEEDED entry on the status topic.

    python3 eval/e2/action_robot.py [--order 6] [--period 5.0]
"""

from __future__ import annotations

import argparse
import sys
import time

import rclpy
from example_interfaces.action import Fibonacci
from rclpy.action import ActionClient, ActionServer
from rclpy.node import Node


class FibonacciRobot(Node):
    def __init__(self, order: int, period: float):
        super().__init__("fibonacci_robot")
        self.order = order
        self.goals_sent = 0
        self._server = ActionServer(self, Fibonacci, "fibonacci", self.execute)
        self._client = ActionClient(self, Fibonacci, "fibonacci")
        self.create_timer(period, self.send_goal)
        self.get_logger().info(
            f"fibonacci demo: goal order={order} every {period:g}s"
        )

    def execute(self, goal_handle):
        sequence = [0, 1]
        feedback = Fibonacci.Feedback()
        for i in range(1, goal_handle.request.order):
            sequence.append(sequence[i] + sequence[i - 1])
            feedback.sequence = sequence
            goal_handle.publish_feedback(feedback)
            time.sleep(0.2)
        goal_handle.succeed()
        result = Fibonacci.Result()
        result.sequence = sequence
        return result

    def send_goal(self) -> None:
        if not self._client.server_is_ready():
            return
        goal = Fibonacci.Goal()
        goal.order = self.order
        self._client.send_goal_async(goal)
        self.goals_sent += 1
        self.get_logger().info(f"GOAL: sent fibonacci order={self.order}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--order", type=int, default=6)
    parser.add_argument("--period", type=float, default=5.0)
    args, ros_args = parser.parse_known_args()
    rclpy.init(args=[sys.argv[0], *ros_args])
    node = FibonacciRobot(args.order, args.period)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
