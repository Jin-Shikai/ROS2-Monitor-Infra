"""
DataRecord: the core data unit flowing through the monitoring pipeline.

Every message captured by a Collector is wrapped into a DataRecord before
entering the TransformerPipeline.  After transformation the same DataRecord
(possibly with trimmed/flattened `data`) is handed to the Dispatcher.

"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def generate_session_id() -> str:
    """Short unique session identifier: date + 8-char UUID fragment."""
    date_part = datetime.now().strftime("%Y%m%d_%H%M%S")
    uuid_part = uuid.uuid4().hex[:8]
    return f"{date_part}_{uuid_part}"


@dataclass
class DataRecord:
    """A single monitoring data point flowing through the pipeline."""

    # --- JSONL record kind ---
    _type: str = "data"           # "session_start" | "data" | "session_end" | "error"

    # --- Session ---
    session_id: str = ""

    # --- Source identity ---
    source_type: str = ""         # "topic" | "service" | "action"
    source_name: str = ""         # e.g. "/cmd_vel", "/navigate_to_pose"
    source_node: list[str] | None = None  # node name(s) of the publisher/server
                                  # topic: all known publishers at subscription time
                                  # service/action: the single server node
    msg_type: str = ""            # e.g. "geometry_msgs/msg/Twist"
    phase: str | None = None      # None for topics
                                  # "request" | "response" for services
                                  # "feedback" | "status" | "goal" | "result" for actions

    # --- Timestamps ---
    timestamp: float = 0.0        # UTC wall-clock (time.time()), when collector received msg
    ros_timestamp: dict | None = None   # {"sec": int, "nanosec": int} from header.stamp

    # --- Payload ---
    data: dict = field(default_factory=dict)  # message content (post-transformer)

    # --- Framework context ---
    metadata: dict = field(default_factory=dict)
    # Expected metadata keys (auto-filled by framework):
    #   "seq": int               -- monotonic record sequence number
    #   "qos_profile": str       -- QoS profile name used for subscription
    #   "transformers_applied": list[str]  -- names of transformers that ran

    # ------------------------------------------------------------------ #
    # Serialization
    # ------------------------------------------------------------------ #

    def to_json(self) -> str:
        """Serialize to a single JSON line (for JSONL output)."""
        d = asdict(self)
        # Drop None values to keep output compact
        # Drop None, empty strings, and empty dicts to keep output compact
        d = {k: v for k, v in d.items()
             if v is not None and v != "" and v != {}}
        return json.dumps(d, default=str, ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> DataRecord:
        """Deserialize from a JSON line."""
        d = json.loads(line)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    # ------------------------------------------------------------------ #
    # Convenience constructors
    # ------------------------------------------------------------------ #

    @classmethod
    def make_session_start(cls, session_id: str, config: dict) -> DataRecord:
        return cls(
            _type="session_start",
            session_id=session_id,
            timestamp=time.time(),
            data=config,
        )

    @classmethod
    def make_session_end(cls, session_id: str, stats: dict | None = None) -> DataRecord:
        return cls(
            _type="session_end",
            session_id=session_id,
            timestamp=time.time(),
            data=stats or {},
        )

    @classmethod
    def from_topic_msg(
        cls,
        session_id: str,
        topic_name: str,
        msg_type: str,
        data: dict,
        seq: int,
        source_node: list[str] | None = None,
    ) -> DataRecord:
        """Create a DataRecord from a topic subscription callback."""
        ros_ts = _extract_ros_timestamp(data)
        return cls(
            _type="data",
            session_id=session_id,
            source_type="topic",
            source_name=topic_name,
            source_node=source_node,
            msg_type=msg_type,
            phase=None,
            timestamp=time.time(),
            ros_timestamp=ros_ts,
            data=data,
            metadata={"seq": seq},
        )

    @classmethod
    def from_service_event(
        cls,
        session_id: str,
        service_name: str,
        msg_type: str,
        event_data: dict,
        seq: int,
        source_node: list[str] | None = None,
    ) -> DataRecord:
        """Create a DataRecord from a service introspection event.

        `event_data` is the dict from message_to_ordereddict() on a *_Event msg.
        Structure: {"info": {...}, "request": [...], "response": [...]}
        """
        info = event_data.get("info", {})

        # event_type: 0=REQUEST_SENT, 1=REQUEST_RECEIVED, 2=RESPONSE_SENT, 3=RESPONSE_RECEIVED
        event_type = info.get("event_type", -1)
        if event_type in (0, 1):
            phase = "request"
            payload_list = event_data.get("request", [])
        else:
            phase = "response"
            payload_list = event_data.get("response", [])

        # Unwrap: the request/response fields are arrays with 0 or 1 element
        payload = payload_list[0] if payload_list else {}

        ros_ts = None
        stamp = info.get("stamp")
        if stamp and (stamp.get("sec", 0) != 0 or stamp.get("nanosec", 0) != 0):
            ros_ts = stamp

        return cls(
            _type="data",
            session_id=session_id,
            source_type="service",
            source_name=service_name,
            source_node=source_node,
            msg_type=msg_type,
            phase=phase,
            timestamp=time.time(),
            ros_timestamp=ros_ts,
            data=payload,
            metadata={
                "seq": seq,
                "event_type": event_type,
                "client_gid": info.get("client_gid"),
                "sequence_number": info.get("sequence_number"),
            },
        )

    @classmethod
    def from_action_feedback(
        cls,
        session_id: str,
        action_name: str,
        msg_type: str,
        feedback_data: dict,
        seq: int,
        source_node: list[str] | None = None,
    ) -> DataRecord:
        """Create a DataRecord from an action feedback hidden topic."""
        ros_ts = _extract_ros_timestamp(feedback_data)
        return cls(
            _type="data",
            session_id=session_id,
            source_type="action",
            source_name=action_name,
            source_node=source_node,
            msg_type=msg_type,
            phase="feedback",
            timestamp=time.time(),
            ros_timestamp=ros_ts,
            data=feedback_data,
            metadata={"seq": seq},
        )

    @classmethod
    def from_action_status(
        cls,
        session_id: str,
        action_name: str,
        status_data: dict,
        seq: int,
        source_node: list[str] | None = None,
    ) -> DataRecord:
        """Create a DataRecord from an action status hidden topic."""
        return cls(
            _type="data",
            session_id=session_id,
            source_type="action",
            source_name=action_name,
            source_node=source_node,
            msg_type="action_msgs/msg/GoalStatusArray",
            phase="status",
            timestamp=time.time(),
            data=status_data,
            metadata={"seq": seq},
        )


def _extract_ros_timestamp(data: dict) -> dict | None:
    """Try to pull header.stamp from a message dict. Returns None if absent."""
    header = data.get("header")
    if not header:
        return None
    stamp = header.get("stamp")
    if not stamp:
        return None
    if stamp.get("sec", 0) == 0 and stamp.get("nanosec", 0) == 0:
        return None  # default-constructed, not meaningful
    return stamp
