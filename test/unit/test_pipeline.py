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
from exporter import Dispatcher, Exporter
from pipeline import (
    build_converter_chain,
    build_converter_stage,
    build_verdict_stage,
)


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


def test_converter_stage_feeds_arbitrary_downstream(logger):
    """The converter half can run detached from the verdict half: it forwards
    DSL records to *any* downstream Dispatcher (here a capturing one standing
    in for a network transport)."""
    captured: list = []

    class _Capture(Exporter):
        def export(self, record) -> None:
            captured.append(record)

    downstream: Dispatcher = Dispatcher(label="capture")
    downstream.add(_Capture())

    spec = ConverterSpec.from_dict({
        "type": "custom.rule_based_converter:RuleBasedConverter",
        "source_match": "^/odom$",
        "field_map": {"velocity": "twist.twist.linear.x"},
        "property_id": "speed",
    })
    outer = build_converter_stage(spec, downstream, logger)
    assert outer is not None

    raw: Dispatcher = Dispatcher(label="raw")
    raw.add(outer)
    raw.export(DataRecord.from_topic_msg(
        session_id="S", topic_name="/odom",
        msg_type="nav_msgs/msg/Odometry",
        data={"twist.twist.linear.x": 0.4}, seq=1,
    ))

    assert len(captured) == 1
    assert captured[0]["velocity"] == 0.4
    assert captured[0]["_property_id"] == "speed"


def test_verdict_stage_consumes_transported_dsl_record(logger, tmp_path):
    """The verdict half can run from a DSL record alone (as if it arrived over
    a transport), with no converter in the process."""
    spec = ConverterSpec.from_dict({
        "type": "custom.rule_based_converter:RuleBasedConverter",
        "verdict": {
            "type": "custom.threshold_verdict:ThresholdVerdict",
            "property_id": "speed",
            "field": "velocity",
            "op": ">",
            "threshold": 0.2,
            "sustain_sec": 0.0,
            "exporters": [{"type": "file", "path": "v_{session_id}.jsonl"}],
        },
    })
    stage = build_verdict_stage(spec, str(tmp_path), "S", logger)
    assert stage is not None
    dsl_dispatcher, verdict_dispatcher = stage

    # Hand the verdict stage a DSL record directly — the shape a converter on
    # another host would have published.
    dsl_dispatcher.export({"velocity": 0.4, "_property_id": "speed", "_timestamp": 1.0})
    verdict_dispatcher.close_all()
    dsl_dispatcher.close_all()

    out = (tmp_path / "v_S.jsonl").read_text().strip().splitlines()
    assert len(out) == 1
    assert '"property_id": "speed"' in out[0]
    assert '"result": false' in out[0]


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
