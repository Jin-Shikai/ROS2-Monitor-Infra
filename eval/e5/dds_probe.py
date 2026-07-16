#!/usr/bin/env python3
"""Publish a low-rate PC wall-clock probe for the E5 PC-to-Pi DDS metric.

The Nav2 messages use simulation time, so their ROS header stamps cannot be
compared with the Pi collector's wall clock. This auxiliary PoseStamped uses
``time.time_ns()`` in its header; the Pi DataRecord timestamp then measures
the DDS/LAN delivery time after correcting the measured PC/Pi clock offset.
It does not feed any E5 property.
"""

from __future__ import annotations

import argparse
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node


class DDSProbe(Node):
    def __init__(self, rate_hz: float) -> None:
        super().__init__("e5_dds_probe")
        self.publisher = self.create_publisher(PoseStamped, "/e5/dds_probe", 10)
        self.sequence = 0
        self.timer = self.create_timer(1.0 / rate_hz, self.publish_probe)

    def publish_probe(self) -> None:
        wall_ns = time.time_ns()
        msg = PoseStamped()
        msg.header.stamp.sec = wall_ns // 1_000_000_000
        msg.header.stamp.nanosec = wall_ns % 1_000_000_000
        msg.header.frame_id = "pc_wall_clock"
        self.sequence += 1
        msg.pose.position.x = float(self.sequence)
        msg.pose.orientation.w = 1.0
        self.publisher.publish(msg)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rate", type=float, default=5.0)
    args = parser.parse_args()
    if args.rate <= 0:
        parser.error("--rate must be positive")

    rclpy.init()
    node = DDSProbe(args.rate)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
