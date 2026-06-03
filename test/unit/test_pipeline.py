"""Unit tests for monitor/pipeline.py — extracted DSL chain builder.

These tests cover DSL chain construction plus a verdict-runner-side smoke
test that drives a complete chain with a `Dispatcher[DataRecord]` standing
in for the MonitorNode raw dispatcher.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

import pytest

from config_model import ConverterSpec
from data_record import DataRecord
from exporter import Dispatcher
from pipeline import build_converter_chain


@pytest.fixture
def logger():
    return logging.getLogger("test_pipeline")


def test_missing_type_returns_none(logger, tmp_path):
    spec = ConverterSpec.from_dict({})
    assert build_converter_chain(spec, str(tmp_path), "sid", logger) is None


def test_missing_verdict_section_returns_none(logger, tmp_path):
    spec = {"type": "custom.rule_based_converter:RuleBasedConverter"}
    spec = ConverterSpec.from_dict(spec)
    assert build_converter_chain(spec, str(tmp_path), "sid", logger) is None


def test_unresolvable_converter_returns_none(logger, tmp_path):
    spec = {
        "type": "no.such.module:Nope",
        "verdict": {"type": "custom.threshold_verdict:ThresholdVerdict"},
    }
    spec = ConverterSpec.from_dict(spec)
    assert build_converter_chain(spec, str(tmp_path), "sid", logger) is None


def test_session_id_substituted_in_verdict_exporter_path(logger, tmp_path):
    """`{session_id}` in any string kwarg of a verdict exporter spec
    resolves against the chain's session id, and relative paths root
    at `output_dir`."""
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
            "exporters": [
                {"type": "file", "path": "verdicts_{session_id}.jsonl"},
            ],
        },
    }
    spec = ConverterSpec.from_dict(spec)
    built = build_converter_chain(spec, str(tmp_path), "abc123", logger)
    assert built is not None
    _, verdict_dispatcher = built
    exporters = verdict_dispatcher.exporters
    assert len(exporters) == 1
    assert cast(Any, exporters[0]).path == Path(tmp_path) / "verdicts_abc123.jsonl"
    verdict_dispatcher.close_all()


def test_new_exporters_schema_with_file_and_stdout(logger, tmp_path):
    """The new `verdict.exporters: [...]` schema builds one Exporter per
    entry, fanning out via the Dispatcher[Verdict]."""
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
            "exporters": [
                {"type": "file", "path": "v_{session_id}.jsonl"},
                {"type": "stdout"},
            ],
        },
    }
    spec = ConverterSpec.from_dict(spec)
    built = build_converter_chain(spec, str(tmp_path), "S", logger)
    assert built is not None
    _, verdict_dispatcher = built
    assert verdict_dispatcher.size == 2
    verdict_dispatcher.close_all()


def test_end_to_end_chain_writes_verdict_on_breach(logger, tmp_path):
    """Drive a record through the chain and confirm a violation Verdict
    reaches the VerdictFileExporter."""
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
            "exporters": [{"type": "file", "path": "v_{session_id}.jsonl"}],
        },
    }
    spec = ConverterSpec.from_dict(spec)
    built = build_converter_chain(spec, str(tmp_path), "S", logger)
    assert built is not None
    converter_exporter, verdict_dispatcher = built

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
    raw.export(rec)
    verdict_dispatcher.close_all()

    out = (tmp_path / "v_S.jsonl").read_text().strip().splitlines()
    assert len(out) == 1
    assert '"property_id": "speed"' in out[0]
    assert '"result": false' in out[0]


def test_inputs_filter_drops_other_sources(logger, tmp_path):
    """A converter with `inputs: ["/cmd_vel"]` must not see /odom records."""
    spec = {
        "type": "custom.nav2_case1.cmd_vel_speed_converter:CmdVelSpeedConverter",
        "inputs": ["/cmd_vel"],
        "verdict": {
            "type": "custom.nav2_case1.cmd_vel_speed_verdict:CmdVelSpeedVerdict",
            "exporters": [{"type": "file", "path": "v_{session_id}.jsonl"}],
        },
    }
    spec = ConverterSpec.from_dict(spec)
    built = build_converter_chain(spec, str(tmp_path), "S", logger)
    assert built is not None
    outer, verdict_dispatcher = built

    raw: Dispatcher = Dispatcher(label="raw")
    raw.add(outer)

    # /odom should be filtered out by inputs even though its data shape would
    # otherwise match (twist.linear.x present).
    raw.export(DataRecord.from_topic_msg(
        session_id="S", topic_name="/odom",
        msg_type="nav_msgs/msg/Odometry",
        data={"twist.linear.x": 0.99}, seq=1,
    ))
    # /cmd_vel with a breach should fire.
    raw.export(DataRecord.from_topic_msg(
        session_id="S", topic_name="/cmd_vel",
        msg_type="geometry_msgs/msg/Twist",
        data={"twist.linear.x": 0.5}, seq=2,
    ))
    verdict_dispatcher.close_all()

    out = (tmp_path / "v_S.jsonl").read_text().strip().splitlines()
    assert len(out) == 1, f"expected exactly one verdict (from /cmd_vel), got {len(out)}"
    assert '"value": 0.5' in out[0]


def test_inputs_empty_list_rejected(logger, tmp_path):
    spec = {
        "type": "custom.nav2_case1.cmd_vel_speed_converter:CmdVelSpeedConverter",
        "inputs": [],
        "verdict": {
            "type": "custom.nav2_case1.cmd_vel_speed_verdict:CmdVelSpeedVerdict",
            "exporters": [{"type": "stdout"}],
        },
    }
    spec = ConverterSpec.from_dict(spec)
    assert build_converter_chain(spec, str(tmp_path), "S", logger) is None


def test_inputs_wrong_type_rejected(logger, tmp_path):
    spec = {
        "type": "custom.nav2_case1.cmd_vel_speed_converter:CmdVelSpeedConverter",
        "inputs": "/cmd_vel",  # must be a list, not a bare string
        "verdict": {
            "type": "custom.nav2_case1.cmd_vel_speed_verdict:CmdVelSpeedVerdict",
            "exporters": [{"type": "stdout"}],
        },
    }
    spec = ConverterSpec.from_dict(spec)
    assert build_converter_chain(spec, str(tmp_path), "S", logger) is None


def test_unknown_verdict_exporter_type_returns_none(logger, tmp_path):
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
            "exporters": [{"type": "nope"}],
        },
    }
    spec = ConverterSpec.from_dict(spec)
    assert build_converter_chain(spec, str(tmp_path), "S", logger) is None
