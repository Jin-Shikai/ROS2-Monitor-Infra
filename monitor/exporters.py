"""DataRecord exporter registry and resolver."""

from __future__ import annotations

from data_record import DataRecord
from exporter import Exporter, FileExporter
from exporter_mqtt import MQTTExporter
from plugins import resolve_plugin_class


DATA_RECORD_EXPORTER_REGISTRY: dict[str, type[Exporter[DataRecord]]] = {
    "file": FileExporter,
    "mqtt": MQTTExporter,
}


def resolve_data_record_exporter_class(type_str: str) -> type[Exporter[DataRecord]]:
    return resolve_plugin_class(
        type_str,
        DATA_RECORD_EXPORTER_REGISTRY,
        Exporter,
        "DataRecord exporter",
    )
