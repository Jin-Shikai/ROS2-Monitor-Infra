"""Data Collector layer.

Subscribes to ROS2 sources (topics / service events / action hidden topics),
wraps each incoming message into a DataRecord, runs it through the per-collector
TransformerPipeline, and exports the result.

Source-node resolution rule (UNKNOWN-retry):
    DDS discovery may not have resolved the publisher's node name by the time
    the first callback fires; it then returns a placeholder like
    "_NODE_NAMESPACE_UNKNOWN_/_NODE_NAME_UNKNOWN_". Never cache a placeholder;
    keep retrying on subsequent callbacks until a real name resolves.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from rosidl_runtime_py import message_to_ordereddict
from rosidl_runtime_py.utilities import get_message, get_service

from data_record import DataRecord
from transformer import TransformerPipeline


UNKNOWN_MARKER = "UNKNOWN"


class DataCollector(ABC):
    """Abstract base for every monitoring source."""

    def __init__(
        self,
        node: Node,
        session_id: str,
        source_name: str,
        pipeline: TransformerPipeline,
        export: Callable[[DataRecord], None],
    ):
        self.node = node
        self.session_id = session_id
        self.source_name = source_name
        self.pipeline = pipeline
        self.export = export
        self._seq = 0
        # Per-topic cache of resolved publisher node names. Key absent = not yet
        # resolved (retry on next callback); value = confirmed node list.
        self._source_nodes_cache: dict[str, list[str]] = {}

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _emit(self, record: DataRecord) -> None:
        out = self.pipeline.process(record)
        if out is not None:
            self.export(out)

    def _resolve_nodes(self, topic_name: str) -> list[str] | None:
        """Return publisher node names for `topic_name`, applying UNKNOWN-retry.

        Returns None (caller uses this as source_node) until the first clean
        resolution, after which the result is cached for the collector's lifetime.
        """
        cached = self._source_nodes_cache.get(topic_name)
        if cached is not None:
            return cached
        try:
            infos = self.node.get_publishers_info_by_topic(topic_name)
        except Exception:
            return None
        if not infos:
            return None
        if any(UNKNOWN_MARKER in (info.node_name or "") for info in infos):
            return None
        nodes: list[str] = []
        for info in infos:
            ns = (info.node_namespace or "").rstrip("/")
            name = info.node_name
            nodes.append(f"{ns}/{name}" if ns else name)
        self._source_nodes_cache[topic_name] = nodes
        return nodes


class TopicCollector(DataCollector):
    """Direct subscription to a regular topic."""

    def __init__(
        self,
        node: Node,
        session_id: str,
        source_name: str,
        msg_type_str: str,
        pipeline: TransformerPipeline,
        export: Callable[[DataRecord], None],
        qos: int = 10,
    ):
        super().__init__(node, session_id, source_name, pipeline, export)
        self.msg_type_str = msg_type_str
        self.qos = qos
        self._subscription = None

    def start(self) -> None:
        msg_cls = get_message(self.msg_type_str)
        self._subscription = self.node.create_subscription(
            msg_cls, self.source_name, self._on_msg, self.qos
        )

    def stop(self) -> None:
        if self._subscription is not None:
            self.node.destroy_subscription(self._subscription)
            self._subscription = None

    def _on_msg(self, msg) -> None:
        data = dict(message_to_ordereddict(msg))
        record = DataRecord.from_topic_msg(
            session_id=self.session_id,
            topic_name=self.source_name,
            msg_type=self.msg_type_str,
            data=data,
            seq=self._next_seq(),
            source_node=self._resolve_nodes(self.source_name),
        )
        self._emit(record)


class ServiceCollector(DataCollector):
    """Subscribe to a service's introspection event hidden topic.

    The remote service node must have introspection enabled (CONTENTS mode) for
    events to appear on /<service>/_service_event.
    """

    def __init__(
        self,
        node: Node,
        session_id: str,
        source_name: str,
        service_type_str: str,
        pipeline: TransformerPipeline,
        export: Callable[[DataRecord], None],
    ):
        super().__init__(node, session_id, source_name, pipeline, export)
        self.service_type_str = service_type_str
        self._event_topic = f"{source_name}/_service_event"
        self._subscription = None

    def start(self) -> None:
        srv_cls = get_service(self.service_type_str)
        event_cls = srv_cls.Event
        qos = QoSProfile(
            depth=50,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._subscription = self.node.create_subscription(
            event_cls, self._event_topic, self._on_event, qos
        )

    def stop(self) -> None:
        if self._subscription is not None:
            self.node.destroy_subscription(self._subscription)
            self._subscription = None

    def _on_event(self, msg) -> None:
        data = dict(message_to_ordereddict(msg))
        record = DataRecord.from_service_event(
            session_id=self.session_id,
            service_name=self.source_name,
            msg_type=f"{self.service_type_str}_Event",
            event_data=data,
            seq=self._next_seq(),
            source_node=self._resolve_nodes(self._event_topic),
        )
        self._emit(record)


class ActionCollector(DataCollector):
    """Subscribe to action feedback and/or status hidden topics.

    This collector supports feedback and status phases. Goal/result/cancel
    phases require server-side introspection and are not collected here.
    """

    def __init__(
        self,
        node: Node,
        session_id: str,
        source_name: str,
        action_type_str: str,
        phases: list[str],
        pipeline: TransformerPipeline,
        export: Callable[[DataRecord], None],
    ):
        super().__init__(node, session_id, source_name, pipeline, export)
        self.action_type_str = action_type_str
        self.phases = set(phases) if phases else {"feedback", "status"}
        self._feedback_topic = f"{source_name}/_action/feedback"
        self._status_topic = f"{source_name}/_action/status"
        self._feedback_sub = None
        self._status_sub = None

    def start(self) -> None:
        if "feedback" in self.phases:
            from rosidl_runtime_py.utilities import get_action
            action_cls = get_action(self.action_type_str)
            feedback_msg_cls = action_cls.Impl.FeedbackMessage
            self._feedback_sub = self.node.create_subscription(
                feedback_msg_cls, self._feedback_topic, self._on_feedback, 10
            )
        if "status" in self.phases:
            from action_msgs.msg import GoalStatusArray
            self._status_sub = self.node.create_subscription(
                GoalStatusArray, self._status_topic, self._on_status, 10
            )

    def stop(self) -> None:
        for sub in (self._feedback_sub, self._status_sub):
            if sub is not None:
                self.node.destroy_subscription(sub)
        self._feedback_sub = None
        self._status_sub = None

    def _on_feedback(self, msg) -> None:
        data = dict(message_to_ordereddict(msg))
        record = DataRecord.from_action_feedback(
            session_id=self.session_id,
            action_name=self.source_name,
            msg_type=f"{self.action_type_str}_FeedbackMessage",
            feedback_data=data,
            seq=self._next_seq(),
            source_node=self._resolve_nodes(self._feedback_topic),
        )
        self._emit(record)

    def _on_status(self, msg) -> None:
        data = dict(message_to_ordereddict(msg))
        record = DataRecord.from_action_status(
            session_id=self.session_id,
            action_name=self.source_name,
            status_data=data,
            seq=self._next_seq(),
            source_node=self._resolve_nodes(self._status_topic),
        )
        self._emit(record)


class CollectorManager:
    """Owns a set of DataCollector instances, starts/stops them uniformly."""

    def __init__(
        self,
        node: Node,
        session_id: str,
        export: Callable[[DataRecord], None],
    ):
        self.node = node
        self.session_id = session_id
        self.export = export
        self.collectors: list[DataCollector] = []

    def register(self, collector: DataCollector) -> None:
        self.collectors.append(collector)

    def start_all(self) -> None:
        for c in self.collectors:
            c.start()

    def stop_all(self) -> None:
        for c in self.collectors:
            try:
                c.stop()
            except Exception as ex:
                self.node.get_logger().warn(
                    f"Collector {c.source_name} stop failed: {ex}"
                )
