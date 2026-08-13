"""Data Converter layer — framework abstractions only.

A DataConverter turns a DataRecord into either a DSL-ready record (any type,
consumed by a VerdictService) or a derived DataRecord (consumed by a
downstream converter). The framework supplies only the abstract base class
and the transport adapter (`ConverterExporter`). Real converters live outside
the framework — see `custom/` for example implementations and the YAML config
form (`module.path:ClassName`).

Besides the reactive `convert()` path, a converter may override
`start(emit)` / `stop()` to produce records on its own schedule (timers,
windows, watchdogs). `emit` accepts the same values `convert()` may return
and is safe to call from any thread.
"""

from __future__ import annotations

import json
import logging
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable

from data_record import DataRecord
from exporter import Dispatcher, Exporter
from plugins import resolve_plugin_class

# Per-record converter I/O tracing. Off at the default INFO level; the WebUI
# enables it (CONVERTER_IO_LOG=DEBUG) so the dashboard can show what each
# converter consumed and produced.
_io_logger = logging.getLogger("converter_io")


class DataConverter(ABC):
    """Convert a DataRecord into a DSL-ready record or a derived DataRecord.

    Return None to drop the record (e.g. it doesn't match this converter's
    source filter, or it lacks required fields).
    """

    name: str = "DataConverter"

    @abstractmethod
    def convert(self, record: DataRecord) -> Any | None: ...

    def start(self, emit: Callable[[Any], None]) -> None:
        """Called once after wiring. Override and keep `emit` to produce
        records outside the `convert()` callback (timers, watchdogs)."""

    def stop(self) -> None:
        """Called once on shutdown. Override to cancel timers/threads."""


class ConverterExporter(Exporter[DataRecord]):
    """Adapter: presents a (DataConverter + downstream Dispatcher) pair as an
    Exporter, so it can be plugged into the raw record dispatcher.

    Session bookend records (`session_start` / `session_end`) are skipped.
    `convert()` calls and self-scheduled `emit()` calls are serialized by one
    lock, so converter state and this chain's downstream never see concurrent
    access.
    """

    def __init__(self, converter: DataConverter, downstream: Dispatcher, label: str = ""):
        self.converter = converter
        self.downstream = downstream
        self.label = label or type(converter).__name__
        self._lock = threading.Lock()
        self.converter.start(self._emit)

    def _log_io(self, direction: str, payload: Any) -> None:
        if not _io_logger.isEnabledFor(logging.DEBUG):
            return
        if isinstance(payload, DataRecord):
            text = payload.to_json()
        else:
            try:
                text = json.dumps(payload, default=str, ensure_ascii=False)
            except (TypeError, ValueError):
                text = str(payload)
        _io_logger.debug("[Converter%s %s] %s", direction, self.label, text)

    def _emit(self, result: Any) -> None:
        if result is None:
            return
        with self._lock:
            self._log_io("Output", result)
            self.downstream.export(result)

    def export(self, record: Any) -> None:
        if isinstance(record, DataRecord) and record._type != "data":
            return
        with self._lock:
            self._log_io("Input", record)
            result = self.converter.convert(record)
            if result is None:
                return
            self._log_io("Output", result)
            self.downstream.export(result)

    def flush(self) -> None:
        self.downstream.flush_all()

    def close(self) -> None:
        self.converter.stop()
        self.downstream.close_all()


def resolve_converter_class(spec: str) -> type[DataConverter]:
    """Resolve a converter class from a 'module.path:ClassName' import string.

    Example: 'custom.rule_based:RuleBasedConverter'
    """
    if ":" not in spec:
        raise ValueError(
            f"Bad converter spec '{spec}'. Expected 'module.path:ClassName' "
            f"(e.g. 'custom.rule_based:RuleBasedConverter')."
        )
    return resolve_plugin_class(spec, {}, DataConverter, "converter")
