"""Unit tests for monitor/exporter.py.

MQTTExporter tests live in test_exporter_mqtt.py.
"""

import json
from pathlib import Path

import pytest

from data_record import DataRecord
from exporter import Exporter, Dispatcher, FileExporter


def _rec(seq=1):
    return DataRecord.from_topic_msg(
        session_id="sid", topic_name="/t", msg_type="m",
        data={"v": seq}, seq=seq,
    )


def test_file_exporter_writes_jsonl(tmp_path):
    exp = FileExporter(output_dir=str(tmp_path), session_id="sess", flush_every=1)
    try:
        exp.export(_rec(1))
        exp.export(_rec(2))
    finally:
        exp.close()

    path = tmp_path / "sess.jsonl"
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    rows = [json.loads(l) for l in lines]
    assert rows[0]["data"] == {"v": 1}
    assert rows[1]["data"] == {"v": 2}


def test_file_exporter_creates_output_dir(tmp_path):
    nested = tmp_path / "a" / "b"
    exp = FileExporter(output_dir=str(nested), session_id="s")
    try:
        exp.export(_rec())
    finally:
        exp.close()
    assert (nested / "s.jsonl").exists()


def test_file_exporter_close_is_idempotent(tmp_path):
    exp = FileExporter(output_dir=str(tmp_path), session_id="s")
    exp.export(_rec())
    exp.close()
    exp.close()  # must not raise


def test_file_exporter_flush_every_batches_flushes(tmp_path):
    exp = FileExporter(output_dir=str(tmp_path), session_id="s", flush_every=3)
    try:
        for i in range(5):
            exp.export(_rec(i))
    finally:
        exp.close()
    # All 5 must be visible after close()
    assert len((tmp_path / "s.jsonl").read_text().strip().splitlines()) == 5


def test_dispatcher_registry_and_build():
    d = Dispatcher()
    d.register("file", FileExporter)
    assert d.has("file")
    assert not d.has("nope")
    with pytest.raises(KeyError):
        d.build("nope")


def test_dispatcher_fans_out_to_all(tmp_path):
    class Recorder(Exporter):
        def __init__(self):
            self.records = []
        def export(self, record):
            self.records.append(record)

    d = Dispatcher()
    a, b = Recorder(), Recorder()
    d.add(a)
    d.add(b)
    r = _rec(1)
    d.dispatch(r)
    assert a.records == [r]
    assert b.records == [r]


def test_dispatcher_isolates_exporter_exceptions(capsys):
    class Boom(Exporter):
        def export(self, record):
            raise RuntimeError("broken")

    class Recorder(Exporter):
        def __init__(self):
            self.count = 0
        def export(self, record):
            self.count += 1

    d = Dispatcher()
    d.add(Boom())
    good = Recorder()
    d.add(good)
    d.dispatch(_rec())
    assert good.count == 1
    assert "broken" in capsys.readouterr().out


def test_dispatcher_flush_and_close_all_tolerate_errors():
    class Boom(Exporter):
        def export(self, record): pass
        def flush(self): raise RuntimeError()
        def close(self): raise RuntimeError()

    d = Dispatcher()
    d.add(Boom())
    d.flush_all()  # must not raise
    d.close_all()  # must not raise


