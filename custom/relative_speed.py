from __future__ import annotations

import math

from converter import DataConverter
from data_record import DataRecord
from transformer import _get_path


class RelativeSpeedConverter(DataConverter):
    name = "RelativeSpeedConverter"

    def __init__(
        self,
        robot_a: str | None = None,
        robot_b: str | None = None,
        components: list[str] | None = None,
        property_id: str = "fleet_relative_speed",
    ):
        self.robot_a = robot_a.rstrip("/") if robot_a else None
        self.robot_b = robot_b.rstrip("/") if robot_b else None
        self.components = list(components) if components else [
            "twist.twist.linear.x",
            "twist.twist.linear.y",
        ]
        self.property_id = property_id
        self._velocity: dict[str, tuple[list[float], str, float]] = {}

    def convert(self, record: DataRecord) -> dict | None:
        robot = self._robot_for(record.source_name)
        if robot is None:
            return None
        velocity: list[float] = []
        for path in self.components:
            value = _field(record.data, path)
            if value is None:
                return None
            velocity.append(float(value))
        self._velocity[robot] = (velocity, record.record_id, record.timestamp)
        if self.robot_a is None or self.robot_b is None or len(self._velocity) < 2:
            return None
        va, aid, ats = self._velocity[self.robot_a]
        vb, bid, bts = self._velocity[self.robot_b]
        return {
            "relative_speed": math.hypot(*(a - b for a, b in zip(va, vb))),
            "_property_id": self.property_id,
            "_timestamp": max(ats, bts),
            "_input_record_ids": [aid, bid],
            "_source_name": "fleet",
        }

    def _robot_for(self, source_name: str) -> str | None:
        for robot in (self.robot_a, self.robot_b):
            if robot and source_name == f"{robot}/odom":
                return robot
        if not source_name.endswith("/odom"):
            return None
        robot = source_name[: -len("/odom")].rstrip("/")
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


def _field(data: dict, path: str):
    if path in data:
        return data[path]
    found, value = _get_path(data, path)
    return value if found else None
