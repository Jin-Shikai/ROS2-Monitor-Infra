"""Fleet minimum-separation property over two robots' odometry streams.

`SeparationDistanceConverter` pairs the most recent position of each robot
(taken from the namespaced `/amcl_pose` topics by default, so both positions
are expressed in the shared map frame) and emits the Euclidean distance
between them whenever either robot reports a new position. It is the
position-based counterpart of `RelativeSpeedConverter`: that converter
compares velocities, this one compares poses, which is what a separation
predicate needs.

`SeparationDistanceVerdict` turns the distance stream into an edge-triggered
verdict stream: a Verdict is emitted only when the fleet crosses the
`min_distance` threshold (violation when the robots get closer than the
threshold, recovery when they separate again).
"""

from __future__ import annotations

import math
import time
from typing import Any

from converter import DataConverter
from data_record import DataRecord
from transformer import _get_path
from verdict import Verdict, VerdictService


class SeparationDistanceConverter(DataConverter):
    name = "SeparationDistanceConverter"

    def __init__(
        self,
        robot_a: str | None = None,
        robot_b: str | None = None,
        components: list[str] | None = None,
        topic_suffix: str = "/amcl_pose",
        property_id: str = "fleet_separation",
    ):
        self.robot_a = robot_a.rstrip("/") if robot_a else None
        self.robot_b = robot_b.rstrip("/") if robot_b else None
        # Positions must share one frame: AMCL poses are in the map frame,
        # whereas each robot's /odom frame is anchored at its own spawn point.
        self.topic_suffix = topic_suffix
        self.components = list(components) if components else [
            "pose.pose.position.x",
            "pose.pose.position.y",
        ]
        self.property_id = property_id
        self._position: dict[str, tuple[list[float], str, float]] = {}

    def convert(self, record: DataRecord) -> dict | None:
        robot = self._robot_for(record.source_name)
        if robot is None:
            return None
        position: list[float] = []
        for path in self.components:
            value = _field(record.data, path)
            if value is None:
                return None
            position.append(float(value))
        self._position[robot] = (position, record.record_id, record.timestamp)
        if self.robot_a is None or self.robot_b is None or len(self._position) < 2:
            return None
        pa, aid, ats = self._position[self.robot_a]
        pb, bid, bts = self._position[self.robot_b]
        return {
            "separation_m": math.hypot(*(a - b for a, b in zip(pa, pb))),
            "positions": {self.robot_a: pa, self.robot_b: pb},
            "_property_id": self.property_id,
            "_timestamp": max(ats, bts),
            "_input_record_ids": [aid, bid],
            "_source_name": "fleet",
        }

    def _robot_for(self, source_name: str) -> str | None:
        for robot in (self.robot_a, self.robot_b):
            if robot and source_name == f"{robot}{self.topic_suffix}":
                return robot
        if not source_name.endswith(self.topic_suffix):
            return None
        robot = source_name[: -len(self.topic_suffix)].rstrip("/")
        if not robot:
            return None
        if self.robot_a is None:
            self.robot_a = robot
            return robot
        if self.robot_b is None and robot != self.robot_a:
            self.robot_b = robot
            return robot
        if robot in {self.robot_a, self.robot_b}:
            return robot
        return None


class SeparationDistanceVerdict(VerdictService):
    name = "SeparationDistanceVerdict"

    def __init__(self, min_distance: float = 1.0, property_id: str | None = None):
        self.min_distance = float(min_distance)
        self.property_id = property_id
        self._violating = False

    def evaluate(self, dsl_record: Any) -> Verdict | None:
        if not isinstance(dsl_record, dict) or "separation_m" not in dsl_record:
            return None
        try:
            value = float(dsl_record["separation_m"])
        except (TypeError, ValueError):
            return None
        violating = value < self.min_distance
        if violating == self._violating:
            return None
        self._violating = violating
        return Verdict(
            timestamp=float(dsl_record.get("_timestamp", time.time())),
            property_id=str(
                self.property_id or dsl_record.get("_property_id") or "fleet_separation"
            ),
            result=not violating,
            details={
                "separation_m": value,
                "min_distance": self.min_distance,
                "positions": dsl_record.get("positions"),
            },
        )


def _field(data: dict, path: str):
    if path in data:
        return data[path]
    found, value = _get_path(data, path)
    return value if found else None
