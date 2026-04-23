"""Unit tests for monitor/transformer.py."""

import time

import pytest

from data_record import DataRecord
from transformer import (
    FieldExtractor,
    OnChangeFilter,
    RateThrottler,
    Transformer,
    TransformerPipeline,
)


def _make(data):
    return DataRecord(_type="data", session_id="s", source_type="topic",
                      source_name="/x", msg_type="m", timestamp=0.0,
                      data=data, metadata={"seq": 1})


def test_field_extractor_scalar_path():
    rec = _make({"pose": {"position": {"x": 1.0, "y": 2.0, "z": 3.0}}})
    out = FieldExtractor(["pose.position.x", "pose.position.y"]).transform(rec)
    assert out is not None
    assert out.data == {"pose.position.x": 1.0, "pose.position.y": 2.0}


def test_field_extractor_flattens_dict_subtree():
    rec = _make({"twist": {"linear": {"x": 0.1, "y": 0.0}}})
    out = FieldExtractor(["twist.linear"]).transform(rec)
    assert out is not None
    assert out.data == {"twist.linear.x": 0.1, "twist.linear.y": 0.0}


def test_field_extractor_missing_path_skipped():
    rec = _make({"a": 1})
    out = FieldExtractor(["nope.nope"]).transform(rec)
    assert out is not None
    assert out.data == {}


def test_rate_throttler_drops_within_window():
    rt = RateThrottler(max_rate_hz=1000.0)  # 1ms interval
    first = rt.transform(_make({"v": 1}))
    second = rt.transform(_make({"v": 2}))  # too soon
    assert first is not None
    assert second is None


def test_rate_throttler_allows_after_interval():
    rt = RateThrottler(max_rate_hz=1000.0)  # 1 ms
    assert rt.transform(_make({})) is not None
    time.sleep(0.005)
    assert rt.transform(_make({})) is not None


def test_rate_throttler_rejects_non_positive():
    with pytest.raises(ValueError):
        RateThrottler(max_rate_hz=0)
    with pytest.raises(ValueError):
        RateThrottler(max_rate_hz=-1)


def test_onchange_first_pass_always_emits():
    f = OnChangeFilter(["k"])
    assert f.transform(_make({"k": 1})) is not None


def test_onchange_drops_unchanged():
    f = OnChangeFilter(["k"])
    f.transform(_make({"k": 1}))
    assert f.transform(_make({"k": 1})) is None


def test_onchange_emits_on_change():
    f = OnChangeFilter(["k"])
    f.transform(_make({"k": 1}))
    assert f.transform(_make({"k": 2})) is not None
    # back-to-same drops
    assert f.transform(_make({"k": 2})) is None


def test_pipeline_records_applied_transformer_names():
    pl = TransformerPipeline([FieldExtractor(["a"])])
    out = pl.process(_make({"a": 1, "b": 2}))
    assert out is not None
    assert out.metadata["transformers_applied"] == ["FieldExtractor"]
    assert out.data == {"a": 1}


def test_pipeline_short_circuits_on_none():
    class DropAll(Transformer):
        name = "DropAll"
        def transform(self, record):
            del record
            return None

    pl = TransformerPipeline([DropAll(), FieldExtractor(["a"])])
    assert pl.process(_make({"a": 1})) is None


def test_pipeline_empty_chain_leaves_metadata_alone():
    pl = TransformerPipeline([])
    out = pl.process(_make({"a": 1}))
    assert out is not None
    assert "transformers_applied" not in out.metadata
    assert out.data == {"a": 1}
