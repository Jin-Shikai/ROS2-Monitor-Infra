"""Unit tests for monitor/converter.py — framework abstractions only.

For tests of the command-speed demo converter, see test_custom_speed_converter.py.
"""

import pytest

from data_record import DataRecord
from converter import (
    ConverterExporter,
    DataConverter,
    resolve_converter_class,
)
from exporter import Dispatcher, Exporter


class _ConstConverter(DataConverter):
    def __init__(self, payload):
        self.payload = payload
    def convert(self, record):
        return self.payload


class _NoneConverter(DataConverter):
    def convert(self, record):
        return None


def _data_record(rtype="data"):
    if rtype == "session_start":
        return DataRecord.make_session_start("sid", {})
    if rtype == "session_end":
        return DataRecord.make_session_end("sid", {})
    return DataRecord.from_topic_msg(
        session_id="sid", topic_name="/t", msg_type="m",
        data={"v": 1}, seq=1,
    )


def test_data_converter_is_abstract():
    with pytest.raises(TypeError):
        DataConverter()  # pyright: ignore[reportAbstractUsage]


def test_converter_exporter_dispatches_result():
    class Capture(Exporter):
        def __init__(self):
            self.items = []
        def export(self, record):
            self.items.append(record)

    downstream = Dispatcher()
    cap = Capture()
    downstream.add(cap)
    ce = ConverterExporter(_ConstConverter({"k": 1}), downstream)
    ce.export(_data_record())
    assert cap.items == [{"k": 1}]


def test_converter_exporter_drops_when_convert_returns_none():
    class Capture(Exporter):
        def __init__(self):
            self.items = []
        def export(self, record):
            self.items.append(record)

    downstream = Dispatcher()
    cap = Capture()
    downstream.add(cap)
    ce = ConverterExporter(_NoneConverter(), downstream)
    ce.export(_data_record())
    assert cap.items == []


def test_converter_exporter_skips_session_bookends():
    class Capture(Exporter):
        def __init__(self):
            self.items = []
        def export(self, record):
            self.items.append(record)

    downstream = Dispatcher()
    cap = Capture()
    downstream.add(cap)
    ce = ConverterExporter(_ConstConverter({"x": 1}), downstream)

    ce.export(_data_record("session_start"))
    ce.export(_data_record("session_end"))
    assert cap.items == []


def test_converter_exporter_close_propagates():
    closed = []
    class Closeable(Exporter):
        def export(self, record): pass
        def close(self): closed.append(True)
    downstream = Dispatcher()
    downstream.add(Closeable())
    ce = ConverterExporter(_ConstConverter({}), downstream)
    ce.close()
    assert closed == [True]


def test_converter_lifecycle_start_emit_stop():
    class Capture(Exporter):
        def __init__(self):
            self.items = []
        def export(self, record):
            self.items.append(record)

    class SelfScheduled(DataConverter):
        def __init__(self):
            self.stopped = False
            self._emit = None
        def convert(self, record):
            return None
        def start(self, emit):
            self._emit = emit
        def stop(self):
            self.stopped = True

    downstream = Dispatcher()
    cap = Capture()
    downstream.add(cap)
    conv = SelfScheduled()
    ce = ConverterExporter(conv, downstream)

    assert conv._emit is not None
    conv._emit({"tick": 1})
    conv._emit(None)  # None emissions are dropped
    assert cap.items == [{"tick": 1}]

    ce.close()
    assert conv.stopped


def test_converter_exporter_passes_non_datarecord_payloads():
    """Chained converters may receive whatever the upstream emitted."""
    class Capture(Exporter):
        def __init__(self):
            self.items = []
        def export(self, record):
            self.items.append(record)

    class DictConverter(DataConverter):
        def convert(self, record):
            return {"seen": record}

    downstream = Dispatcher()
    cap = Capture()
    downstream.add(cap)
    ce = ConverterExporter(DictConverter(), downstream)
    ce.export({"upstream": True})
    assert cap.items == [{"seen": {"upstream": True}}]


def test_resolve_requires_module_path():
    with pytest.raises(ValueError):
        resolve_converter_class("CmdVelSpeedConverter")


def test_resolve_module_path_works():
    cls = resolve_converter_class(
        "custom.speed:CmdVelSpeedConverter"
    )
    assert issubclass(cls, DataConverter)


def test_resolve_module_path_wrong_type_raises():
    with pytest.raises(TypeError):
        resolve_converter_class("data_record:DataRecord")
