"""Source registry + resolver — symmetric counterpart of `verdict_exporters`.

Each `Source[DataRecord]` implementation is registered here under a short
name (e.g. `mqtt`) so YAML can pick the inbound transport the same way the
verdict side picks an outbound `Exporter[Verdict]`. User-defined sources
(replay-from-file, socket, ROS2 topic, ...) are referenced from YAML by
`type: module.path:ClassName`.
"""

from __future__ import annotations

from plugins import resolve_plugin_class
from source import Source
from source_mqtt import MQTTSource


SOURCE_REGISTRY: dict[str, type[Source]] = {
    "mqtt": MQTTSource,
}


def resolve_source_class(type_str: str) -> type[Source]:
    """Resolve a Source class from either a registry name (e.g. 'mqtt') or
    a 'module.path:ClassName' import string for user-defined sources.
    """
    return resolve_plugin_class(type_str, SOURCE_REGISTRY, Source, "source")
