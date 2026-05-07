"""Unit tests for monitor/pipeline.py — extracted DSL chain builder.

These tests cover the same logic that was previously embedded in
monitor_node._build_converter_chain, plus a verdict-runner-side smoke test
that drives a complete chain with a `Dispatcher[DataRecord]` standing in
for the MonitorNode raw dispatcher.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from data_record import DataRecord
from exporter import Dispatcher
from pipeline import build_converter_chain


@pytest.fixture
def logger():
    return logging.getLogger("test_pipeline")


def test_missing_type_returns_none(logger, tmp_path):
    assert build_converter_chain({}, str(tmp_path), "sid", logger) is None


def test_missing_verdict_section_returns_none(logger, tmp_path):
    spec = {"type": "custom.rule_based_converter:RuleBasedConverter"}
    assert build_converter_chain(spec, str(tmp_path), "sid", logger) is None


def test_unresolvable_converter_returns_none(logger, tmp_path):
    spec = {
        "type": "no.such.module:Nope",
        "verdict": {"type": "custom.threshold_verdict:ThresholdVerdict"},
    }
    assert build_converter_chain(spec, str(tmp_path), "sid", logger) is None


def test_session_id_substituted_in_verdict_output_path(logger, tmp_path):
    spec = {
        "type": "custom.rule_based_converter:RuleBasedConverter",
        "source_match": "^/odom$",
        "field_map": {"velocity": "twist.twist.linear.x"},
        "property_id": "p1",
        "verdict": {
            "type": "custom.threshold_verdict:ThresholdVerdict",
            "property_id": "p1",
            "field": "velocity",
            "op": ">",
            "threshold": 0.2,
            "output": "verdicts_{session_id}.jsonl",
        },
    }
    built = build_converter_chain(spec, str(tmp_path), "abc123", logger)
    assert built is not None
    _, sinks = built
    assert len(sinks) == 1
    assert sinks[0].path == Path(tmp_path) / "verdicts_abc123.jsonl"
    sinks[0].close()


def test_end_to_end_chain_writes_verdict_on_breach(logger, tmp_path):
    """Drive a record through the chain returned by build_converter_chain
    and confirm a violation Verdict reaches the FileVerdictSink."""
    spec = {
        "type": "custom.rule_based_converter:RuleBasedConverter",
        "source_match": "^/odom$",
        "field_map": {"velocity": "twist.twist.linear.x"},
        "property_id": "speed",
        "verdict": {
            "type": "custom.threshold_verdict:ThresholdVerdict",
            "property_id": "speed",
            "field": "velocity",
            "op": ">",
            "threshold": 0.2,
            "sustain_sec": 0.0,
            "output": "v_{session_id}.jsonl",
        },
    }
    built = build_converter_chain(spec, str(tmp_path), "S", logger)
    assert built is not None
    converter_exporter, sinks = built

    raw: Dispatcher = Dispatcher(label="raw")
    raw.add(converter_exporter)

    # Phase-2 FieldExtractor produces flat dot-keyed dicts.
    rec = DataRecord.from_topic_msg(
        session_id="S",
        topic_name="/odom",
        msg_type="nav_msgs/msg/Odometry",
        data={"twist.twist.linear.x": 0.4},  # > 0.2 ⇒ violation
        seq=1,
    )
    raw.dispatch(rec)
    for s in sinks:
        s.close()

    out = (tmp_path / "v_S.jsonl").read_text().strip().splitlines()
    assert len(out) == 1
    assert '"property_id": "speed"' in out[0]
    assert '"result": false' in out[0]
