"""Centralised global predicate over the latest positions of two robots."""

from __future__ import annotations

import math
from typing import Any

from converter import DataConverter
from data_record import DataRecord
from transformer import _get_path
from verdict import Verdict, VerdictService


class FleetDistanceConverter(DataConverter):
    def __init__(self, robot_a: str, robot_b: str):
        self.robot_a = robot_a.rstrip("/")
        self.robot_b = robot_b.rstrip("/")
        self._positions: dict[str, tuple[float, float, str, float]] = {}

    def convert(self, record: DataRecord) -> dict | None:
        robot = next(
            (r for r in (self.robot_a, self.robot_b) if record.source_name == f"{r}/odom"),
            None,
        )
        if robot is None:
            return None
        x = _field(record.data, "pose.pose.position.x")
        y = _field(record.data, "pose.pose.position.y")
        if x is None or y is None:
            return None
        self._positions[robot] = (float(x), float(y), record.record_id, record.timestamp)
        if len(self._positions) < 2:
            return None
        ax, ay, aid, ats = self._positions[self.robot_a]
        bx, by, bid, bts = self._positions[self.robot_b]
        return {
            "distance": math.hypot(ax - bx, ay - by),
            "_timestamp": max(ats, bts),
            "_input_record_ids": [aid, bid],
            "_source_name": "fleet",
        }


class MinimumFleetDistanceVerdict(VerdictService):
    def __init__(self, minimum_distance: float = 1.0):
        self.minimum_distance = float(minimum_distance)
        self._fired = False

    def evaluate(self, record: Any) -> Verdict | None:
        if not isinstance(record, dict) or "distance" not in record:
            return None
        distance = float(record["distance"])
        violated = distance < self.minimum_distance
        if violated == self._fired:
            return None
        self._fired = violated
        return Verdict(
            timestamp=float(record.get("_timestamp", 0.0)),
            property_id="fleet_minimum_distance",
            result=not violated,
            details={"distance": distance, "minimum_distance": self.minimum_distance},
        )


def _field(data: dict, path: str):
    if path in data:
        return data[path]
    found, value = _get_path(data, path)
    return value if found else None
