"""Centralised global predicate over the latest velocities of two robots."""

from __future__ import annotations

import math
from typing import Any

from converter import DataConverter
from data_record import DataRecord
from transformer import _get_path


class RelativeSpeedConverter(DataConverter):
    """Join `<robot>/odom` velocity streams of two robots and emit their
    relative speed `|v_a - v_b|` as a DSL record.

    Pair with e.g. `custom.threshold:ThresholdVerdict`
    (`field: relative_speed, op: ">", threshold: 0.5`).
    """

    name = "RelativeSpeedConverter"

    def __init__(
        self,
        robot_a: str,
        robot_b: str,
        components: list[str] | None = None,
        property_id: str = "fleet_relative_speed",
    ):
        self.robot_a = robot_a.rstrip("/")
        self.robot_b = robot_b.rstrip("/")
        self.components = list(components) if components else [
            "twist.twist.linear.x",
            "twist.twist.linear.y",
        ]
        self.property_id = property_id
        self._velocity: dict[str, tuple[list[float], str, float]] = {}

    def convert(self, record: DataRecord) -> dict | None:
        robot = next(
            (r for r in (self.robot_a, self.robot_b) if record.source_name == f"{r}/odom"),
            None,
        )
        if robot is None:
            return None
        velocity: list[float] = []
        for path in self.components:
            value = _field(record.data, path)
            if value is None:
                return None
            velocity.append(float(value))
        self._velocity[robot] = (velocity, record.record_id, record.timestamp)
        if len(self._velocity) < 2:
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


def _field(data: dict, path: str):
    if path in data:
        return data[path]
    found, value = _get_path(data, path)
    return value if found else None
