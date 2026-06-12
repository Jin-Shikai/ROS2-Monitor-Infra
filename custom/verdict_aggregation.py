"""Aggregate local robot verdicts into a fleet-level verdict."""

from __future__ import annotations

from typing import Any

from converter import DataConverter
from data_record import DataRecord
from verdict import Verdict, VerdictService


class LocalViolationCountConverter(DataConverter):
    def __init__(self):
        self._violating: dict[str, bool] = {}

    def convert(self, record: DataRecord) -> dict | None:
        if record.source_type != "verdict" or "result" not in record.data:
            return None
        self._violating[record.source_name] = not bool(record.data["result"])
        return {
            "violation_count": sum(self._violating.values()),
            "sources": sorted(k for k, v in self._violating.items() if v),
            "_timestamp": record.timestamp,
            "_record_id": record.record_id,
        }


class SimultaneousLocalViolationsVerdict(VerdictService):
    def __init__(self, minimum_count: int = 2):
        self.minimum_count = int(minimum_count)
        self._fired = False

    def evaluate(self, record: Any) -> Verdict | None:
        if not isinstance(record, dict) or "violation_count" not in record:
            return None
        count = int(record["violation_count"])
        violated = count >= self.minimum_count
        if violated == self._fired:
            return None
        self._fired = violated
        return Verdict(
            timestamp=float(record.get("_timestamp", 0.0)),
            property_id="simultaneous_local_violations",
            result=not violated,
            details={"violation_count": count, "sources": record.get("sources", [])},
        )
