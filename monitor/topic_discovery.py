"""
topic_discovery.py

Scans the current ROS2 network for all active topics and prints their names and types.
Use this before editing config.yaml to see what topics are available for monitoring.

Usage:
    source /opt/ros/jazzy/setup.bash
    python3 topic_discovery.py
"""

import rclpy
from rclpy.node import Node
import time


class TopicDiscovery(Node):
    def __init__(self):
        super().__init__('topic_discovery_helper')

    def get_all_topics(self) -> list[tuple[str, str]]:
        """
        Returns all currently visible topics as [(topic_name, type_string), ...].
        Waits briefly for DDS discovery to complete.
        """
        time.sleep(1.0)
        topic_list = self.get_topic_names_and_types()
        result = []
        for name, types in topic_list:
            if types:
                result.append((name, types[0]))
        return result


def main():
    rclpy.init()
    node = TopicDiscovery()

    print("\n=== Active ROS2 Topics ===")
    print(f"{'Topic Name':<45} {'Message Type':<45}")
    print("-" * 90)

    topics = node.get_all_topics()
    if not topics:
        print("  (No topics found. Check that ROS_DOMAIN_ID matches your robot nodes.)")
    for name, msg_type in sorted(topics):
        print(f"  {name:<43} {msg_type:<45}")

    print(f"\nFound {len(topics)} topic(s)")
    print("Add the desired names and types to config.yaml to start monitoring.\n")

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
