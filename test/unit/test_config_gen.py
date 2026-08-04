from __future__ import annotations

import json
from pathlib import Path

import pytest

from config_gen import GenerationRequest, project, substitute_variables
from config_model import MonitorConfig, RunnerConfig


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("experiment", "variables", "expected_hosts"),
    [
        ("e1", {"RUN_DIR": "/tmp/e1"}, {"monitor"}),
        ("e2", {"RUN_DIR": "/tmp/e2"}, {"monitor", "runner"}),
        ("e3", {"RUN_DIR": "/tmp/e3", "DEADLINE": 35}, {"monitor", "runner"}),
        (
            "e4",
            {"RUN_DIR": "/tmp/e4", "SEP_MIN": 1.0, "SPEED_MAX": 0.3},
            {"monitor", "runner"},
        ),
    ],
)
def test_eval_json_projects_to_runtime_configs(experiment, variables, expected_hosts):
    request_path = ROOT / "eval" / experiment / "request.json"
    raw = json.loads(request_path.read_text(encoding="utf-8"))
    generated = project(
        GenerationRequest.from_dict(substitute_variables(raw, variables))
    )

    assert set(generated) == expected_hosts
    monitor = MonitorConfig.from_dict(generated["monitor"].config)
    assert monitor.output_dir == variables["RUN_DIR"]
    assert monitor.exporters[0].type == "file"
    if experiment != "e1":
        assert monitor.exporters[1].type == "mqtt"
        assert monitor.exporters[1].kwargs["publish_bookends"] is True
        runner = RunnerConfig.from_dict(generated["runner"].config)
        assert runner.output_dir == variables["RUN_DIR"]
        assert runner.inputs[0].type == "mqtt"


def test_eval_source_projection_keeps_transformers_and_action_phases():
    raw = json.loads((ROOT / "eval/e3/request.json").read_text(encoding="utf-8"))
    generated = project(GenerationRequest.from_dict(substitute_variables(
        raw, {"RUN_DIR": "/tmp/e3", "DEADLINE": 42}
    )))
    monitor = MonitorConfig.from_dict(generated["monitor"].config)
    runner = RunnerConfig.from_dict(generated["runner"].config)

    odom = next(source for source in monitor.topics if source.name == "/odom")
    action = monitor.actions[0]
    nav_converter = next(c for c in runner.converters if c.id == "nav_goal")
    assert [t.type for t in odom.transformers] == ["FieldExtractor", "RateThrottler"]
    assert action.phases == ["feedback", "status"]
    assert nav_converter.kwargs["deadline_sec"] == 42


def test_exact_variable_tokens_preserve_json_types():
    value = {"number": "@N@", "path": "@PATH@", "label": "run-@N@"}
    assert substitute_variables(value, {"N": 35, "PATH": "/tmp/out"}) == {
        "number": 35,
        "path": "/tmp/out",
        "label": "run-35",
    }
