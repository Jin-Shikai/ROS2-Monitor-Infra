"""Small helpers for resolving configured plugin classes."""

from __future__ import annotations

import importlib
from typing import TypeVar


T = TypeVar("T")


def import_class(path: str) -> type:
    """Import a class from `module.path:ClassName`."""
    if ":" not in path:
        raise ValueError(
            f"Bad plugin spec '{path}'. Expected 'module.path:ClassName'."
        )
    module_path, _, class_name = path.partition(":")
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    if not isinstance(cls, type):
        raise TypeError(f"{path} is not a class")
    return cls


def resolve_plugin_class(
    type_str: str,
    registry: dict[str, type[T]],
    expected_base: type[T],
    role: str,
) -> type[T]:
    """Resolve a configured class from a short registry name or import path."""
    if ":" in type_str:
        cls = import_class(type_str)
        if not issubclass(cls, expected_base):
            raise TypeError(f"{type_str} is not a {expected_base.__name__} subclass")
        return cls
    if type_str not in registry:
        raise KeyError(
            f"Unknown {role} type '{type_str}'. Built-ins: {sorted(registry)}. "
            "For user-defined classes use 'module.path:ClassName'."
        )
    return registry[type_str]
