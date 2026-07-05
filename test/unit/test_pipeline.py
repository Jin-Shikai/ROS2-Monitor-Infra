"""Unit tests for monitor/pipeline.py — the runtime graph builder."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from config_model import ConverterSpec, EndpointSpec, RuntimeLinkSpec, VerdictSpec
from data_record import DataRecord
from pipeline import build_graph, build_verdict_stage


@pytest.fixture
def logger():
    return logging.getLogger("test_pipeline")


def _converter(data: dict) -> ConverterSpec:
    return ConverterSpec.from_dict(data)


def _verdict(data: dict) -> VerdictSpec:
    spec = VerdictSpec.from_dict(data)
    assert spec is not None
    return spec


def _links(*pairs: tuple[str, str]) -> list[RuntimeLinkSpec]:
    return [RuntimeLinkSpec.from_dict({"from": f, "to": t}) for f, t in pairs]


def _odom_record(value: float, seq: int = 1, topic: str = "/odom") -> DataRecord:
    return DataRecord.from_topic_msg(
        session_id="S", topic_name=topic, msg_type="nav_msgs/msg/Odometry",
        data={"twist.twist.linear.x": value}, seq=seq,
    )


SPEED_CONVERTER = {
    "id": "c1",
    "type": "custom.rule_based:RuleBasedConverter",
    "params": {
        "source_match": "^/odom$",
        "field_map": {"speed": "twist.twist.linear.x"},
        "property_id": "p",
    },
}

THRESHOLD_VERDICT = {
    "id": "v1",
    "type": "custom.threshold:ThresholdVerdict",
    "params": {"property_id": "p", "field": "speed", "op": ">", "threshold": 0.2,
               "sustain_sec": 0.0},
    "exporters": [{"type": "file", "path": "v_{session_id}.jsonl"}],
}


def test_end_to_end_graph_writes_verdict_on_breach(logger, tmp_path):
    rt = build_graph(
        [_converter(SPEED_CONVERTER)],
        [_verdict(THRESHOLD_VERDICT)],
        _links(("source:/odom", "converter:c1"), ("converter:c1", "verdict:v1")),
        [],
        str(tmp_path), "S", logger,
    )
    assert rt is not None
    rt.record_entry.export(_odom_record(0.4))
    rt.close()

    out = (tmp_path / "v_S.jsonl").read_text().strip().splitlines()
    assert len(out) == 1
    assert '"property_id": "p"' in out[0]
    assert '"result": false' in out[0]


def test_source_links_filter_other_sources(logger, tmp_path):
    rt = build_graph(
        [_converter(SPEED_CONVERTER)],
        [_verdict(THRESHOLD_VERDICT)],
        _links(("source:/odom", "converter:c1"), ("converter:c1", "verdict:v1")),
        [],
        str(tmp_path), "S", logger,
    )
    assert rt is not None
    rt.record_entry.export(_odom_record(0.9, topic="/other"))
    rt.record_entry.export(_odom_record(0.4, seq=2))
    rt.close()

    out = (tmp_path / "v_S.jsonl").read_text().strip().splitlines()
    assert len(out) == 1


def test_converter_without_target_is_skipped(logger, tmp_path):
    rt = build_graph(
        [_converter(SPEED_CONVERTER)],
        [],
        [],
        [],
        str(tmp_path), "S", logger,
    )
    assert rt is None


def test_unresolvable_converter_is_skipped(logger, tmp_path):
    rt = build_graph(
        [_converter({"id": "bad", "type": "no.such.module:Nope"})],
        [_verdict(THRESHOLD_VERDICT)],
        _links(("converter:bad", "verdict:v1")),
        [],
        str(tmp_path), "S", logger,
    )
    assert rt is None


def test_session_id_substituted_in_verdict_exporter_path(logger, tmp_path):
    stage = build_verdict_stage(_verdict(THRESHOLD_VERDICT), str(tmp_path), "abc123", logger)
    assert stage is not None
    _, verdict_dispatcher = stage
    assert verdict_dispatcher.exporters[0].path == Path(tmp_path) / "v_abc123.jsonl"
    verdict_dispatcher.close_all()


def test_unknown_verdict_exporter_type_fails_stage(logger, tmp_path):
    spec = _verdict({**THRESHOLD_VERDICT, "exporters": [{"type": "nope"}]})
    assert build_verdict_stage(spec, str(tmp_path), "S", logger) is None


def test_verdict_stage_consumes_transported_dsl_record(logger, tmp_path):
    """A verdict fed through input routing evaluates DSL records that arrived
    over a transport, with no converter in the process."""
    rt = build_graph(
        [],
        [_verdict(THRESHOLD_VERDICT)],
        _links(("input:ext", "verdict:v1")),
        [],
        str(tmp_path), "S", logger,
    )
    assert rt is not None
    rt.input_entries["ext"].export({"speed": 0.4, "_property_id": "p", "_timestamp": 1.0})
    rt.close()

    out = (tmp_path / "v_S.jsonl").read_text().strip().splitlines()
    assert len(out) == 1
    assert '"result": false' in out[0]


def test_converter_output_endpoint_archives_dsl(logger, tmp_path):
    outputs = [EndpointSpec.from_dict(
        {"id": "arch", "payload": "dsl", "type": "file", "path": "arch_{session_id}.jsonl"}, 1
    )]
    rt = build_graph(
        [_converter(SPEED_CONVERTER)],
        [],
        _links(("converter:c1", "output:arch")),
        outputs,
        str(tmp_path), "S", logger,
    )
    assert rt is not None
    rt.record_entry.export(_odom_record(0.4))
    rt.close()

    rows = [json.loads(l) for l in (tmp_path / "arch_S.jsonl").read_text().splitlines()]
    assert rows[0]["speed"] == 0.4


def test_verdict_shared_by_two_converters_instantiated_once(logger, tmp_path):
    c2 = dict(SPEED_CONVERTER, id="c2")
    rt = build_graph(
        [_converter(SPEED_CONVERTER), _converter(c2)],
        [_verdict(THRESHOLD_VERDICT)],
        _links(
            ("source:/odom", "converter:c1"),
            ("source:/cmd_vel", "converter:c2"),
            ("converter:c1", "verdict:v1"),
            ("converter:c2", "verdict:v1"),
        ),
        [],
        str(tmp_path), "S", logger,
    )
    assert rt is not None
    # ThresholdVerdict is edge-triggered: a second breach via the other
    # converter must not re-fire because the same instance holds state.
    rt.record_entry.export(_odom_record(0.4, topic="/odom"))
    rt.record_entry.export(_odom_record(0.5, seq=2, topic="/cmd_vel"))
    rt.close()

    out = (tmp_path / "v_S.jsonl").read_text().strip().splitlines()
    assert len(out) == 1
