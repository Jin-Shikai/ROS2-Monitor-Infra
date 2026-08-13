from __future__ import annotations

import time
from typing import Any

from verdict import Verdict, VerdictService


class ThresholdVerdict(VerdictService):
    name = "ThresholdVerdict"

    def __init__(self, threshold: float = 0.3, property_id: str | None = None):
        self.property_id = property_id
        self.threshold = float(threshold)
        self._violating = False

    def evaluate(self, dsl_record: Any) -> Verdict | None:
        if not isinstance(dsl_record, dict):
            return None
        measurement = self._measurement(dsl_record)
        if measurement is None:
            return None
        field, value = measurement
        violating = value > self.threshold
        if violating == self._violating:
            return None
        self._violating = violating
        return Verdict(
            timestamp=float(dsl_record.get("_timestamp", time.time())),
            property_id=str(self.property_id or dsl_record.get("_property_id") or field),
            result=not violating,
            details={
                "field": field,
                "threshold": self.threshold,
                "value": value,
            },
        )

    def _measurement(self, dsl_record: dict[str, Any]) -> tuple[str, float] | None:
        for field, value in dsl_record.items():
            if field.startswith("_"):
                continue
            if isinstance(value, int | float) and not isinstance(value, bool):
                return field, float(value)
        return None
