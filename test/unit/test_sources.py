"""Unit tests for monitor/sources.py — the inbound Source registry/resolver."""

from __future__ import annotations

import pytest

from source import Source
from source_mqtt import MQTTSource
from sources import SOURCE_REGISTRY, resolve_source_class


def test_registry_has_mqtt_builtin():
    assert SOURCE_REGISTRY["mqtt"] is MQTTSource


def test_resolve_builtin_name():
    assert resolve_source_class("mqtt") is MQTTSource


def test_resolve_unknown_name_raises():
    with pytest.raises(KeyError):
        resolve_source_class("nope")


def test_resolve_module_path_works():
    cls = resolve_source_class("source_mqtt:MQTTSource")
    assert issubclass(cls, Source)


def test_resolve_module_path_wrong_type_raises():
    # data_record:DataRecord is importable but is not a Source subclass.
    with pytest.raises(TypeError):
        resolve_source_class("data_record:DataRecord")
