"""Unit tests for monitor/config_gen.py — the generation-request projection.

The two demo requests in ``demo/config_gen/`` are projected to runtime YAML and
checked for *behaviour equivalence* with the hand-written demos:

  * ``all_in_one.json``  ~ ``demo/deploy_mode1`` (one monitor_node process).
  * ``three_host.json``  ~ ``demo/deploy_split_converter_verdict`` (robot
    monitor + split converter/verdict over an MQTT dsl seam).

Equivalence is asserted by feeding the generated dicts through the *same*
parsers and chain builders the real entrypoints use (`MonitorConfig` /
`RunnerConfig` + `pipeline.build_*`) and driving records through, so the test
needs no ROS2. Topic names are derived, so we assert structure + behaviour, not
byte-identity with the checked-in demo YAML.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from config_gen import GenerationRequest, project
from config_model import ConverterSpec, MonitorConfig, RunnerConfig
from data_record import DataRecord
from exporter import Dispatcher, Exporter, FileExporter
from pipeline import build_converter_chain, build_converter_stage, build_verdict_stage
from source_file import FileReplaySource

DEMO_DIR = Path(__file__).resolve().parents[2] / "demo" / "config_gen"

CONVERTER = "custom.speed_aggregate_filter:SpeedAggregateFilter"
VERDICT = "custom.threshold_verdict:ThresholdVerdict"


@pytest.fixture
def logger():
    return logging.getLogger("test_config_gen")


def _load(name: str):
    return project(GenerationRequest.load(str(DEMO_DIR / name)))


# --- all-in-one ------------------------------------------------------------- #

def test_all_in_one_projects_single_monitor_node_file():
    generated = _load("all_in_one.json")
    assert set(generated) == {"robot"}
    gen = generated["robot"]
    assert gen.entrypoint == "monitor_node"
    assert gen.role is None

    cfg = MonitorConfig.from_dict(gen.config)
    assert [t.name for t in cfg.topics] == ["/odom"]
    assert cfg.topics[0].msg_type == "nav_msgs/msg/Odometry"

    assert len(cfg.converters) == 1
    conv = cfg.converters[0]
    assert conv.type == CONVERTER
    assert conv.inputs == ["/odom"]
    assert conv.kwargs["components"] == ["twist.twist.linear.x", "twist.twist.linear.y"]
    assert conv.verdict is not None
    assert conv.verdict.type == VERDICT
    # output_to outlets become verdict exporters (no separate "sink" concept).
    assert [e.type for e in conv.verdict.exporters] == ["stdout", "file"]


def test_all_in_one_chain_runs_and_writes_verdict(logger, tmp_path):
    """The generated converters[] entry resolves and a breaching record yields a
    violation Verdict — same observable behaviour as deploy_mode1."""
    gen = _load("all_in_one.json")["robot"]
    spec = ConverterSpec.from_dict(gen.config["converters"][0])
    # keep only the file exporter so we can read the result deterministically.
    spec.verdict.exporters[:] = [e for e in spec.verdict.exporters if e.type == "file"]

    built = build_converter_chain(spec, str(tmp_path), "S", logger)
    assert built is not None, "generated converter chain must resolve and build"
    converter_exporter, verdict_dispatcher = built

    raw: Dispatcher = Dispatcher(label="raw")
    raw.add(converter_exporter)
    raw.export(DataRecord.from_topic_msg(
        session_id="S", topic_name="/odom",
        msg_type="nav_msgs/msg/Odometry",
        data={"twist.twist.linear.x": 0.4},  # speed 0.4 > 0.3 ⇒ violation
        seq=1,
    ))
    verdict_dispatcher.close_all()

    out = (tmp_path / "verdicts_S.jsonl").read_text().strip().splitlines()
    assert len(out) == 1
    assert '"property_id": "linear_speed"' in out[0]
    assert '"result": false' in out[0]


def test_same_host_uses_no_transport():
    """Co-located runtimes run in-process: an all-in-one host needs no inbound
    transport at all, so the link's transport `kind` is irrelevant — file or
    mqtt, a same-host deployment just runs in one process."""
    gen = _load("all_in_one.json")["robot"]
    assert "verdict_runner" not in gen.config       # no inbound transport source
    assert gen.entrypoint == "monitor_node"


# --- file transport (records via JSONL record/replay) ----------------------- #

def test_file_transport_projects_matching_file_paths():
    generated = _load("file_transport.json")
    robot = MonitorConfig.from_dict(generated["robot"].config)
    verifier = RunnerConfig.from_dict(generated["verifier"].config)

    exp = robot.topics[0].exporters[0]
    assert exp.type == "file"
    exp_path = Path(exp.kwargs["output_dir"]) / (
        f'{exp.kwargs["session_id"]}{exp.kwargs.get("filename_suffix", "")}.jsonl'
    )
    assert verifier.source.type == "file"
    src_path = Path(verifier.source.kwargs["path"])
    assert exp_path == src_path, "file exporter and file source must name one shared file"


def test_file_transport_round_trip_runs(logger, tmp_path):
    """Records written by the generated file exporter are replayed by the generated
    file source through the converter+verdict chain — the file seam runs end to end."""
    generated = _load("file_transport.json")
    exp_kwargs = MonitorConfig.from_dict(generated["robot"].config).topics[0].exporters[0].kwargs
    suffix = exp_kwargs.get("filename_suffix", "")

    # write a breaching /odom record via the generated file exporter (rebased to tmp)
    exp = FileExporter(
        output_dir=str(tmp_path), session_id=exp_kwargs["session_id"], filename_suffix=suffix,
    )
    exp.export(DataRecord.from_topic_msg(
        session_id="S", topic_name="/odom",
        msg_type="nav_msgs/msg/Odometry",
        data={"twist.twist.linear.x": 0.4}, seq=1,
    ))
    exp.close()
    file_path = tmp_path / f'{exp_kwargs["session_id"]}{suffix}.jsonl'

    # replay it via the generated file source into the verifier's chain
    vspec = ConverterSpec.from_dict(generated["verifier"].config["converters"][0])
    built = build_converter_chain(vspec, str(tmp_path), "S", logger)
    assert built is not None
    converter_exporter, verdict_dispatcher = built
    raw: Dispatcher = Dispatcher(label="raw")
    raw.add(converter_exporter)
    FileReplaySource(path=str(file_path))._run(raw)   # synchronous read + feed
    verdict_dispatcher.close_all()

    out = (tmp_path / "verdicts_S.jsonl").read_text().strip().splitlines()
    assert len(out) == 1
    assert '"result": false' in out[0]


# --- three-host split ------------------------------------------------------- #

def test_three_host_projects_three_files():
    generated = _load("three_host.json")
    assert set(generated) == {"robot", "converter_host", "verdict_host"}

    robot = generated["robot"]
    assert robot.entrypoint == "monitor_node"
    rcfg = MonitorConfig.from_dict(robot.config)
    assert rcfg.topics[0].exporters[0].type == "mqtt"
    assert rcfg.topics[0].exporters[0].kwargs["topic_prefix"] == "monitor/"

    conv_host = generated["converter_host"]
    assert (conv_host.entrypoint, conv_host.role) == ("split_runner", "converter")
    ccfg = RunnerConfig.from_dict(conv_host.config)
    assert ccfg.source is not None and ccfg.source.type == "mqtt"
    assert ccfg.source.kwargs["topic_filter"] == "monitor/#"
    assert ccfg.converters[0].dsl_transport["topic"] == "dsl/odom_speed"

    vd_host = generated["verdict_host"]
    assert (vd_host.entrypoint, vd_host.role) == ("split_runner", "verdict")
    vcfg = RunnerConfig.from_dict(vd_host.config)
    assert vcfg.converters[0].dsl_transport["topic"] == "dsl/odom_speed"
    assert vcfg.converters[0].verdict.type == VERDICT


def test_three_host_seam_topic_matches_on_both_halves():
    generated = _load("three_host.json")
    conv = RunnerConfig.from_dict(generated["converter_host"].config)
    vd = RunnerConfig.from_dict(generated["verdict_host"].config)
    assert (
        conv.converters[0].dsl_transport["topic"]
        == vd.converters[0].dsl_transport["topic"]
    ), "the converter and verdict halves must share one dsl seam topic"


def test_three_host_converter_half_emits_dsl_record(logger):
    """The split converter half forwards a DSL record downstream (as it would to
    the transport) — proving the generated converter half is runnable."""
    conv = RunnerConfig.from_dict(_load("three_host.json")["converter_host"].config)
    spec = conv.converters[0]

    captured: list = []

    class _Capture(Exporter):
        def export(self, record) -> None:
            captured.append(record)

    downstream: Dispatcher = Dispatcher(label="capture")
    downstream.add(_Capture())
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
    assert captured[0]["speed"] == 0.4
    assert captured[0]["_property_id"] == "linear_speed"


def test_three_host_verdict_half_runs_from_dsl_record(logger, tmp_path):
    """The split verdict half evaluates a transported DSL record and writes a
    violation — same observable behaviour as the split demo's verdict role."""
    vd = RunnerConfig.from_dict(_load("three_host.json")["verdict_host"].config)
    spec = vd.converters[0]
    spec.verdict.exporters[:] = [e for e in spec.verdict.exporters if e.type == "file"]

    stage = build_verdict_stage(spec, str(tmp_path), "S", logger)
    assert stage is not None
    dsl_dispatcher, verdict_dispatcher = stage
    dsl_dispatcher.export({"speed": 0.4, "_property_id": "linear_speed", "_timestamp": 1.0})
    verdict_dispatcher.close_all()
    dsl_dispatcher.close_all()

    out = (tmp_path / "verdicts_S.jsonl").read_text().strip().splitlines()
    assert len(out) == 1
    assert '"result": false' in out[0]


# --- converter -> converter chain ------------------------------------------- #

DATA_FILTER = "custom.odom_speed_filter:OdomSpeedFilter"
DSL_CONVERTER = "custom.rule_based_converter:RuleBasedConverter"


def test_converter_chain_projects_filter_and_verdict_runner():
    generated = _load("converter_chain.json")
    assert set(generated) == {"robot", "filter_host", "verdict_host"}

    # robot publishes raw DataRecords on the default namespace
    robot = MonitorConfig.from_dict(generated["robot"].config)
    assert robot.topics[0].exporters[0].kwargs["topic_prefix"] == "monitor/"

    # filter host: a data_filter that republishes DataRecords (no verdict)
    fh = generated["filter_host"]
    assert (fh.entrypoint, fh.role) == ("split_runner", "filter")
    fcfg = RunnerConfig.from_dict(fh.config)
    assert fcfg.source.kwargs["topic_filter"] == "monitor/#"
    fspec = fcfg.converters[0]
    assert fspec.type == DATA_FILTER
    assert fspec.verdict is None
    assert fspec.record_transport["topic_prefix"] == "filtered/"

    # verdict host: reads the filtered records, runs dsl_converter + verdict
    vh = generated["verdict_host"]
    assert (vh.entrypoint, vh.role) == ("verdict_runner", None)
    vcfg = RunnerConfig.from_dict(vh.config)
    assert vcfg.source.kwargs["topic_filter"] == "filtered/#"
    assert vcfg.converters[0].type == DSL_CONVERTER
    assert vcfg.converters[0].verdict.type == VERDICT


def test_converter_chain_records_seam_namespace_matches():
    generated = _load("converter_chain.json")
    fcfg = RunnerConfig.from_dict(generated["filter_host"].config)
    vcfg = RunnerConfig.from_dict(generated["verdict_host"].config)
    out_prefix = fcfg.converters[0].record_transport["topic_prefix"]
    in_filter = vcfg.source.kwargs["topic_filter"]
    assert in_filter == out_prefix + "#", "filter output and verdict input must share a namespace"


def test_converter_chain_runs_filter_then_converter_then_verdict(logger, tmp_path):
    """Drive a record through the whole chain in-process: the data_filter emits a
    DataRecord, which the downstream dsl_converter + verdict consume — proving
    converter->converter handoff works end to end (sans broker)."""
    generated = _load("converter_chain.json")
    fspec = RunnerConfig.from_dict(generated["filter_host"].config).converters[0]
    vspec = RunnerConfig.from_dict(generated["verdict_host"].config).converters[0]
    vspec.verdict.exporters[:] = [e for e in vspec.verdict.exporters if e.type == "file"]

    # filter stage: /odom -> DataRecord{ data: {speed} }
    relayed: list = []

    class _Capture(Exporter):
        def export(self, record) -> None:
            relayed.append(record)

    relay: Dispatcher = Dispatcher(label="relay")
    relay.add(_Capture())
    filter_outer = build_converter_stage(fspec, relay, logger)
    assert filter_outer is not None

    raw: Dispatcher = Dispatcher(label="raw")
    raw.add(filter_outer)
    raw.export(DataRecord.from_topic_msg(
        session_id="S", topic_name="/odom",
        msg_type="nav_msgs/msg/Odometry",
        data={"twist.twist.linear.x": 0.4}, seq=1,
    ))
    assert len(relayed) == 1
    relayed_record = relayed[0]
    assert isinstance(relayed_record, DataRecord)        # records payload, not dsl
    assert relayed_record.data == {"speed": 0.4}

    # the relayed DataRecord is consumed by the downstream dsl_converter + verdict
    built = build_converter_chain(vspec, str(tmp_path), "S", logger)
    assert built is not None
    converter_exporter, verdict_dispatcher = built
    downstream: Dispatcher = Dispatcher(label="verdict_in")
    downstream.add(converter_exporter)
    downstream.export(relayed_record)
    verdict_dispatcher.close_all()

    out = (tmp_path / "verdicts_S.jsonl").read_text().strip().splitlines()
    assert len(out) == 1
    assert '"property_id": "linear_speed"' in out[0]
    assert '"result": false' in out[0]
