"""Inbound transport — symmetric counterpart to Exporter.

A Source pulls records from an external transport (file replay, MQTT broker,
TCP socket, ...) and pushes them into a sink callable. It pairs naturally
with a Dispatcher:

    source.start(dispatcher.dispatch)

Implementations should make `start()` non-blocking (background thread or
async loop) and `stop()` idempotent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class Source(ABC, Generic[T]):
    @abstractmethod
    def start(self, sink: Callable[[T], None]) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...
