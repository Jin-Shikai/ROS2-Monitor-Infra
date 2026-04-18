#!/usr/bin/env python3
"""Subscribe to fake_robot's outputs, convert to DataRecord, and print JSONL.

Usage:
    # Terminal 1: start fake_robot
    python3 test/fake_robot.py

    # Terminal 2: run this capture test
    python3 test/capture_test.py

    # Terminal 3 (optional): trigger service/action
    ros2 service call /set_bool std_srvs/srv/SetBool "{data: true}"
    ros2 action send_goal /fibonacci example_interfaces/action/Fibonacci "{order: 8}" --feedback

Captures:
    /odom, /scan, /cmd_vel, /chatter                — topic messages
    /set_bool/_service_event                         — service introspection events
    /fibonacci/_action/feedback, /_action/status      — action hidden topics
"""

import sys
import os

# Add monitor/ to path so we can import data_record
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "monitor"))

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from rosidl_runtime_py import message_to_ordereddict

from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import Twist
from std_msgs.msg import String
from action_msgs.msg import GoalStatusArray

from data_record import DataRecord, generate_session_id

# We need the service event type for SetBool
from std_srvs.srv import SetBool


# Map topic -> (msg_type_class, msg_type_string)
TOPIC_SUBS = {
    "/odom": (Odometry, "nav_msgs/msg/Odometry"),
    "/scan": (LaserScan, "sensor_msgs/msg/LaserScan"),
    "/cmd_vel": (Twist, "geometry_msgs/msg/Twist"),
    "/chatter": (String, "std_msgs/msg/String"),
}

# Service event hidden topics
SERVICE_EVENT_SUBS = {
    "/set_bool/_service_event": (SetBool.Event, "std_srvs/srv/SetBool_Event"),
}

# Action hidden topics
ACTION_FEEDBACK_SUBS = {}  # Populated dynamically if action msg type is available
ACTION_STATUS_SUBS = {
    "/fibonacci/_action/status": "action_msgs/msg/GoalStatusArray",
}


class CaptureNode(Node):
    def __init__(self):
        super().__init__("capture_test")
        self._session_id = generate_session_id()
        self._seq = 0
        self._record_count = 0

        # Print session_start record
        start_rec = DataRecord.make_session_start(self._session_id, {
            "test": "capture_test",
            "topics": list(TOPIC_SUBS.keys()),
            "services": list(SERVICE_EVENT_SUBS.keys()),
            "actions": list(ACTION_STATUS_SUBS.keys()),
        })
        self._print_record(start_rec)

        # Cache for publisher/server node names (populated lazily on first message)
        self._source_nodes: dict[str, list[str] | None] = {}

        # Subscribe to regular topics
        for topic, (msg_cls, msg_type_str) in TOPIC_SUBS.items():
            self.create_subscription(
                msg_cls, topic,
                lambda msg, t=topic, mt=msg_type_str: self._on_topic(msg, t, mt),
                10,
            )
            self.get_logger().info(f"Subscribed to topic: {topic}")

        # Subscribe to service event hidden topics
        # Use transient_local durability to catch events
        event_qos = QoSProfile(
            depth=50,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        for topic, (msg_cls, msg_type_str) in SERVICE_EVENT_SUBS.items():
            self.create_subscription(
                msg_cls, topic,
                lambda msg, t=topic, mt=msg_type_str: self._on_service_event(msg, t, mt),
                event_qos,
            )
            self.get_logger().info(f"Subscribed to service event: {topic}")

        # Subscribe to action status topics
        for topic, msg_type_str in ACTION_STATUS_SUBS.items():
            self.create_subscription(
                GoalStatusArray, topic,
                lambda msg, t=topic: self._on_action_status(msg, t),
                10,
            )
            self.get_logger().info(f"Subscribed to action status: {topic}")

        # Try to subscribe to action feedback
        try:
            from example_interfaces.action import Fibonacci
            feedback_topic = "/fibonacci/_action/feedback"
            self.create_subscription(
                Fibonacci.Impl.FeedbackMessage, feedback_topic,
                lambda msg: self._on_action_feedback(
                    msg, "/fibonacci", "example_interfaces/action/Fibonacci_FeedbackMessage"
                ),
                10,
            )
            self.get_logger().info(f"Subscribed to action feedback: {feedback_topic}")
        except Exception as e:
            self.get_logger().warn(f"Could not subscribe to Fibonacci feedback: {e}")

        self.get_logger().info(
            f"CaptureNode started — session_id={self._session_id}\n"
            f"  Tip: call the service and action to test those paths:\n"
            f"    ros2 service call /set_bool std_srvs/srv/SetBool \"{{data: true}}\"\n"
            f"    ros2 action send_goal /fibonacci example_interfaces/action/Fibonacci \"{{order: 8}}\" --feedback"
        )

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _print_record(self, record: DataRecord):
        """Print JSONL to stdout and count."""
        print(record.to_json(), flush=True)
        self._record_count += 1

    # ------------------------------------------------------------------ #
    # Callbacks
    # ------------------------------------------------------------------ #

    def _get_publisher_nodes(self, topic_name: str) -> list[str] | None:
        """Query publisher node names for a topic. Result is cached after first call."""
        if topic_name not in self._source_nodes:
            infos = self.get_publishers_info_by_topic(topic_name)
            if infos:
                nodes = []
                for info in infos:
                    ns = info.node_namespace.rstrip("/")
                    name = info.node_name
                    nodes.append(f"{ns}/{name}" if ns else name)
                self._source_nodes[topic_name] = nodes
            else:
                self._source_nodes[topic_name] = None  # will retry next call
        return self._source_nodes[topic_name]

    def _get_service_server_nodes(self, service_name: str) -> list[str] | None:
        """Query service server node names. Result is cached after first call."""
        if service_name not in self._source_nodes:
            infos = self.get_service_names_and_types()
            # get_services_info_by_name equivalent: use publishers on _service_event topic
            event_topic = f"{service_name}/_service_event"
            infos = self.get_publishers_info_by_topic(event_topic)
            if infos:
                nodes = []
                for info in infos:
                    ns = info.node_namespace.rstrip("/")
                    name = info.node_name
                    nodes.append(f"{ns}/{name}" if ns else name)
                self._source_nodes[service_name] = nodes
            else:
                self._source_nodes[service_name] = None
        return self._source_nodes[service_name]

    def _on_topic(self, msg, topic_name: str, msg_type: str):
        data = dict(message_to_ordereddict(msg))
        record = DataRecord.from_topic_msg(
            session_id=self._session_id,
            topic_name=topic_name,
            msg_type=msg_type,
            data=data,
            seq=self._next_seq(),
            source_node=self._get_publisher_nodes(topic_name),
        )
        self._print_record(record)

    def _on_service_event(self, msg, topic_name: str, msg_type: str):
        service_name = topic_name.replace("/_service_event", "")
        data = dict(message_to_ordereddict(msg))
        record = DataRecord.from_service_event(
            session_id=self._session_id,
            service_name=service_name,
            msg_type=msg_type,
            event_data=data,
            seq=self._next_seq(),
            source_node=self._get_service_server_nodes(service_name),
        )
        self._print_record(record)

    def _on_action_feedback(self, msg, action_name: str, msg_type: str):
        data = dict(message_to_ordereddict(msg))
        record = DataRecord.from_action_feedback(
            session_id=self._session_id,
            action_name=action_name,
            msg_type=msg_type,
            feedback_data=data,
            seq=self._next_seq(),
            source_node=self._get_publisher_nodes(f"{action_name}/_action/feedback"),
        )
        self._print_record(record)

    def _on_action_status(self, msg, topic_name: str):
        action_name = topic_name.replace("/_action/status", "")
        data = dict(message_to_ordereddict(msg))
        record = DataRecord.from_action_status(
            session_id=self._session_id,
            action_name=action_name,
            status_data=data,
            seq=self._next_seq(),
            source_node=self._get_publisher_nodes(topic_name),
        )
        self._print_record(record)

    def destroy_node(self):
        # Print session_end
        end_rec = DataRecord.make_session_end(self._session_id, {
            "total_records": self._record_count,
        })
        self._print_record(end_rec)
        super().destroy_node()


def main():
    rclpy.init()
    node = CaptureNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
