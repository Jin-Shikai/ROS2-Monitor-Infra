"""Data Transformer layer.

Each Collector owns a TransformerPipeline instance. DataRecords produced by the
collector flow through the chain in order; any transformer may return None to
drop the record (e.g. RateThrottler, OnChangeFilter).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from data_record import DataRecord


class Transformer(ABC):
    name: str = "Transformer"

    @abstractmethod
    def transform(self, record: DataRecord) -> DataRecord | None:
        """Return the (possibly modified) record, or None to drop it."""


class TransformerPipeline:
    """Run a chain of transformers. Short-circuits on the first None return."""

    def __init__(self, chain: list[Transformer] | None = None):
        self.chain: list[Transformer] = list(chain) if chain else []

    def process(self, record: DataRecord) -> DataRecord | None:
        applied: list[str] = []
        for t in self.chain:
            record = t.transform(record)
            if record is None:
                return None
            applied.append(t.name)
        if applied:
            record.metadata.setdefault("transformers_applied", []).extend(applied)
        return record


def _flatten(value: Any, prefix: str) -> dict[str, Any]:
    """Flatten a nested dict into dot-notation keys under `prefix`. Non-dicts
    become `{prefix: value}`.
    """
    if not isinstance(value, dict):
        return {prefix: value}
    out: dict[str, Any] = {}
    for k, v in value.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        else:
            out[key] = v
    return out


def _get_path(d: Any, path: str) -> tuple[bool, Any]:
    """Walk `path` (dot notation) into nested dict `d`. Returns (found, value)."""
    cur: Any = d
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False, None
    return True, cur


class FieldExtractor(Transformer):
    """Keep only the listed fields; output is flat, dot-notation keyed."""

    name = "FieldExtractor"

    def __init__(self, fields: list[str]):
        self.fields = list(fields)

    def transform(self, record: DataRecord) -> DataRecord | None:
        extracted: dict[str, Any] = {}
        for path in self.fields:
            found, value = _get_path(record.data, path)
            if not found:
                continue
            if isinstance(value, dict):
                extracted.update(_flatten(value, path))
            else:
                extracted[path] = value
        record.data = extracted
        return record


class RateThrottler(Transformer):
    """Drop records that arrive faster than `max_rate_hz` (per-collector state)."""

    name = "RateThrottler"

    def __init__(self, max_rate_hz: float):
        rate = float(max_rate_hz)
        if rate <= 0:
            raise ValueError("max_rate_hz must be > 0")
        self.min_interval = 1.0 / rate
        self._last_emit = 0.0

    def transform(self, record: DataRecord) -> DataRecord | None:
        now = time.monotonic()
        if now - self._last_emit >= self.min_interval:
            self._last_emit = now
            return record
        return None


class OnChangeFilter(Transformer):
    """Pass a record only if at least one watched field changed since the last pass."""

    name = "OnChangeFilter"

    def __init__(self, watch_fields: list[str]):
        self.watch_fields = list(watch_fields)
        self._prev: dict[str, Any] = {}
        self._seen = False

    def transform(self, record: DataRecord) -> DataRecord | None:
        current: dict[str, Any] = {}
        for path in self.watch_fields:
            found, v = _get_path(record.data, path)
            if found:
                current[path] = v
        if not self._seen:
            self._seen = True
            self._prev = current
            return record
        if current != self._prev:
            self._prev = current
            return record
        return None
