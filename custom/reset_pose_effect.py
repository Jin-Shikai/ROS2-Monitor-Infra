from __future__ import annotations

import math
import threading
import time
from typing import Any, Callable

from converter import DataConverter
from data_record import DataRecord
from transformer import _get_path
from verdict import Verdict, VerdictService


class ResetPoseEffectConverter(DataConverter):
    name = "ResetPoseEffectConverter"

    def __init__(
        self,
        service_name: str = "/reset_pose",
        odom_name: str = "/odom",
        deadline_sec: float = 1.0,
        tolerance_m: float = 0.05,
        property_id: str = "reset_pose_effect",
    ):
        self.service_name = service_name
        self.odom_name = odom_name
        self.deadline_sec = float(deadline_sec)
        self.tolerance_m = float(tolerance_m)
        self.property_id = property_id
        self.pending = None
        self.latest_odom = None
        self.emit = None
        self.stop_event = threading.Event()
        self.thread = None

    def convert(self, record: DataRecord) -> dict | None:
        if record.source_name == self.service_name and record.phase == "response":
            if record.data.get("success") is True:
                self.pending = {
                    "time": record.timestamp,
                    "record_id": record.record_id,
                    "sequence_number": record.metadata.get("sequence_number"),
                }
            return None

        if record.source_name != self.odom_name:
            return None
        distance = self._distance(record)
        self.latest_odom = (record.record_id, record.timestamp, distance)
        if self.pending and distance <= self.tolerance_m:
            return self._result(True, record.timestamp, distance)
        if self.pending and record.timestamp - self.pending["time"] > self.deadline_sec:
            return self._result(False, record.timestamp, distance)
        return None

    def start(self, emit: Callable[[Any], None]) -> None:
        self.emit = emit
        self.thread = threading.Thread(target=self._watch, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1.0)

    def _watch(self) -> None:
        while not self.stop_event.wait(0.05):
            if self.pending and time.time() - self.pending["time"] > self.deadline_sec:
                distance = self.latest_odom[2] if self.latest_odom else None
                self.emit(self._result(False, time.time(), distance))

    def _distance(self, record: DataRecord) -> float:
        x = _field(record.data, "pose.pose.position.x")
        y = _field(record.data, "pose.pose.position.y")
        return math.hypot(float(x), float(y))

    def _result(self, ok: bool, ts: float, distance: float | None) -> dict:
        pending = self.pending
        self.pending = None
        ids = [pending["record_id"]]
        if self.latest_odom:
            ids.append(self.latest_odom[0])
        return {
            "reset_effect_ok": ok,
            "elapsed_sec": ts - pending["time"],
            "distance_to_origin": distance,
            "deadline_sec": self.deadline_sec,
            "tolerance_m": self.tolerance_m,
            "sequence_number": pending["sequence_number"],
            "_property_id": self.property_id,
            "_timestamp": ts,
            "_source_name": "reset_pose_effect",
            "_input_record_ids": ids,
        }


class ResetPoseEffectVerdict(VerdictService):
    name = "ResetPoseEffectVerdict"

    def __init__(self, property_id: str = "reset_pose_effect"):
        self.property_id = property_id

    def evaluate(self, record: Any) -> Verdict | None:
        if not isinstance(record, dict):
            return None
        return Verdict(
            timestamp=float(record["_timestamp"]),
            property_id=self.property_id,
            result=bool(record["reset_effect_ok"]),
            details={
                "elapsed_sec": record["elapsed_sec"],
                "distance_to_origin": record["distance_to_origin"],
                "deadline_sec": record["deadline_sec"],
                "tolerance_m": record["tolerance_m"],
                "sequence_number": record["sequence_number"],
            },
        )


def _field(data: dict, path: str):
    if path in data:
        return data[path]
    found, value = _get_path(data, path)
    return value if found else 0.0
