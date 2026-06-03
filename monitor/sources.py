"""Source registry + resolver — symmetric counterpart of `verdict_exporters`.

Each `Source[DataRecord]` implementation is registered here under a short
name (e.g. `mqtt`) so YAML can pick the inbound transport the same way the
verdict side picks an outbound `Exporter[Verdict]`. User-defined sources
(replay-from-file, socket, ROS2 topic, ...) are referenced from YAML by
`type: module.path:ClassName`.
"""

from __future__ import annotations

import importlib

from source import Source
from source_mqtt import MQTTSource


SOURCE_REGISTRY: dict[str, type[Source]] = {
    "mqtt": MQTTSource,
}


def resolve_source_class(type_str: str) -> type[Source]:
    """Resolve a Source class from either a registry name (e.g. 'mqtt') or
    a 'module.path:ClassName' import string for user-defined sources.
    """
    if ":" in type_str:
        module_path, _, class_name = type_str.partition(":")
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        if not (isinstance(cls, type) and issubclass(cls, Source)):
            raise TypeError(
                f"{type_str} is not a Source subclass; cannot be used as a "
                f"verdict-runner source."
            )
        return cls
    if type_str not in SOURCE_REGISTRY:
        raise KeyError(
            f"Unknown source type '{type_str}'. "
            f"Built-ins: {sorted(SOURCE_REGISTRY)}. "
            f"For user-defined sources use 'module.path:ClassName'."
        )
    return SOURCE_REGISTRY[type_str]
