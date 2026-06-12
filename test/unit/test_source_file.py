from __future__ import annotations

import time

from data_record import DataRecord
from exporter import Exporter
from source_file import FileReplaySource


class _ListExporter(Exporter[DataRecord]):
    def __init__(self):
        self.items = []

    def export(self, record):
        self.items.append(record)


def test_file_replay_source_reads_jsonl(tmp_path):
    path = tmp_path / "records.jsonl"
    path.write_text(
        DataRecord.from_topic_msg("s", "/odom", "t", {"v": 1}, 1).to_json() + "\n",
        encoding="utf-8",
    )
    out = _ListExporter()
    source = FileReplaySource(str(path))
    source.start(out)
    for _ in range(50):
        if out.items:
            break
        time.sleep(0.01)
    source.stop()
    assert out.items[0].source_name == "/odom"
