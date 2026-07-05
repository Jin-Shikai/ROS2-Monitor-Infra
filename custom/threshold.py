"""Example VerdictService — copy and adapt for your DSL engine (LTL/STL/CTL/...).

Demonstrates the minimal contract:
  - Subclass `VerdictService` and implement `evaluate(dsl_record) -> Verdict | None`
  - Return None to stay silent; emit a Verdict only on state transitions
    (e.g. breach onset, breach cleared) so a sustained violation produces
    one Verdict, not one per incoming record.

Wire-up: see custom/rule_based.py for the full config example.
"""

from __future__ import annotations

import operator
from typing import Any, Callable

from verdict import Verdict, VerdictService


_OPS: dict[str, Callable[[Any, Any], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}


class ThresholdVerdict(VerdictService):
    """Emit a violation Verdict when `dsl_record[field] <op> threshold` holds.

    Optional `sustain_sec` requires the breach to persist for that duration
    before firing — useful to suppress single-record glitches. The service is
    edge-triggered: one violation Verdict at breach onset, one cleared Verdict
    when the value returns inside the bound.

    Expects `dsl_record` to be a dict containing at least `field`. The
    `_timestamp` key (added by RuleBasedConverter) is used for the sustain
    window; if absent, current wall-clock time is used.
    """

    name = "ThresholdVerdict"

    def __init__(
        self,
        property_id: str,
        field: str,
        op: str,
        threshold: float,
        sustain_sec: float = 0.0,
    ):
        if op not in _OPS:
            raise ValueError(f"Unknown op '{op}'; must be one of {list(_OPS)}")
        self.property_id = property_id
        self.field = field
        self.op = op
        self._cmp = _OPS[op]
        self.threshold = float(threshold)
        self.sustain_sec = float(sustain_sec)
        self._breach_started_at: float | None = None
        self._fired = False

    def evaluate(self, dsl_record: Any) -> Verdict | None:
        import time
        if not isinstance(dsl_record, dict) or self.field not in dsl_record:
            return None
        value = dsl_record[self.field]
        ts = dsl_record.get("_timestamp", time.time())
        breached = self._cmp(value, self.threshold)

        if breached:
            if self._breach_started_at is None:
                self._breach_started_at = ts
            duration = ts - self._breach_started_at
            if not self._fired and duration >= self.sustain_sec:
                self._fired = True
                return Verdict(
                    timestamp=ts,
                    property_id=self.property_id,
                    result=False,
                    details={
                        "field": self.field,
                        "op": self.op,
                        "threshold": self.threshold,
                        "value": value,
                        "duration_sec": duration,
                    },
                )
            return None

        if self._fired:
            self._fired = False
            self._breach_started_at = None
            return Verdict(
                timestamp=ts,
                property_id=self.property_id,
                result=True,
                details={
                    "field": self.field,
                    "value": value,
                    "note": "breach cleared",
                },
            )
        self._breach_started_at = None
        return None
