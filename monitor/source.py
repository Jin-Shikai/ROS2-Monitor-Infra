"""Inbound transport — symmetric counterpart to Exporter.

A Source pulls records from an external transport (file replay, MQTT broker,
TCP socket, ROS2 topic, ...) and pushes them into a downstream
`Exporter[T]` — typically a `Dispatcher[T]` so the same record fans out to
several places.

    source.start(dispatcher)

Implementations should make `start()` non-blocking (background thread or
async loop) and `stop()` idempotent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from exporter import Exporter

T = TypeVar("T")


class Source(ABC, Generic[T]):
    @abstractmethod
    def start(self, exporter: Exporter[T]) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...
