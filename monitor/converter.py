"""Data Converter layer — framework abstractions only.

A DataConverter turns a DataRecord into a DSL-ready record (any type) suitable
for a paired VerdictService. The framework supplies only the abstract base
class and the transport adapter (`ConverterExporter`). Real DSL converters
(LTL, STL, CTL, ...) live outside the framework — see `custom/` for example
implementations and the YAML config form (`module.path:ClassName`).

ConverterExporter is the bridge that lets a Converter participate in the
generic Dispatcher transport layer:

  Dispatcher[DataRecord] -> ConverterExporter -> Dispatcher[Any] -> VerdictExporter
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from data_record import DataRecord
from exporter import Dispatcher, Exporter
from plugins import resolve_plugin_class


class DataConverter(ABC):
    """Convert a DataRecord into a DSL-ready record.

    Return None to drop the record (e.g. it doesn't match this converter's
    source filter, or it lacks required fields).
    """

    name: str = "DataConverter"

    @abstractmethod
    def convert(self, record: DataRecord) -> Any | None: ...


class ConverterExporter(Exporter[DataRecord]):
    """Adapter: presents a (DataConverter + downstream Dispatcher) pair as an
    Exporter[DataRecord], so it can be plugged into the raw dispatcher.

    Session bookend records (`session_start` / `session_end`) are skipped.
    """

    def __init__(self, converter: DataConverter, downstream: Dispatcher):
        self.converter = converter
        self.downstream = downstream

    def export(self, record: DataRecord) -> None:
        if record._type != "data":
            return
        result = self.converter.convert(record)
        if result is None:
            return
        self.downstream.export(result)

    def flush(self) -> None:
        self.downstream.flush_all()

    def close(self) -> None:
        self.downstream.close_all()


def resolve_converter_class(spec: str) -> type[DataConverter]:
    """Resolve a converter class from a 'module.path:ClassName' import string.

    Example: 'custom.rule_based_converter:RuleBasedConverter'
    """
    if ":" not in spec:
        raise ValueError(
            f"Bad converter spec '{spec}'. Expected 'module.path:ClassName' "
            f"(e.g. 'custom.rule_based_converter:RuleBasedConverter')."
        )
    return resolve_plugin_class(spec, {}, DataConverter, "converter")
