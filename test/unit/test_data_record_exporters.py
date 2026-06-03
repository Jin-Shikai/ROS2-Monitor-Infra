"""Unit tests for DataRecord exporter registry/resolver."""

from __future__ import annotations

import pytest

from exporter import Exporter, FileExporter
from exporter_mqtt import MQTTExporter
from exporters import DATA_RECORD_EXPORTER_REGISTRY, resolve_data_record_exporter_class


def test_data_record_exporter_registry_has_builtins():
    assert DATA_RECORD_EXPORTER_REGISTRY["file"] is FileExporter
    assert DATA_RECORD_EXPORTER_REGISTRY["mqtt"] is MQTTExporter


def test_resolve_data_record_exporter_builtin():
    assert resolve_data_record_exporter_class("file") is FileExporter


def test_resolve_data_record_exporter_module_path():
    cls = resolve_data_record_exporter_class("exporter:StdoutExporter")
    assert issubclass(cls, Exporter)


def test_resolve_data_record_exporter_wrong_type_raises():
    with pytest.raises(TypeError):
        resolve_data_record_exporter_class("data_record:DataRecord")
