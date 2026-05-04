"""Tests for custom/threshold_verdict.py (the user-facing demo)."""

import pytest

from custom.threshold_verdict import ThresholdVerdict


def test_fires_violation_on_breach():
    v = ThresholdVerdict("speed", "velocity", ">", 0.5)
    out = v.evaluate({"velocity": 0.7, "_timestamp": 1.0})
    assert out is not None
    assert out.result is False
    assert out.details["value"] == 0.7
    assert out.details["threshold"] == 0.5


def test_silent_below_breach():
    v = ThresholdVerdict("p", "velocity", ">", 0.5)
    assert v.evaluate({"velocity": 0.2, "_timestamp": 1.0}) is None


def test_emits_only_on_state_transition():
    v = ThresholdVerdict("p", "velocity", ">", 0.5)
    a = v.evaluate({"velocity": 0.7, "_timestamp": 1.0})
    b = v.evaluate({"velocity": 0.8, "_timestamp": 1.1})
    c = v.evaluate({"velocity": 0.9, "_timestamp": 1.2})
    assert a is not None and a.result is False
    assert b is None
    assert c is None


def test_clear_after_breach():
    v = ThresholdVerdict("p", "velocity", ">", 0.5)
    v.evaluate({"velocity": 0.7, "_timestamp": 1.0})
    cleared = v.evaluate({"velocity": 0.2, "_timestamp": 2.0})
    assert cleared is not None and cleared.result is True


def test_sustain_window():
    v = ThresholdVerdict("p", "velocity", ">", 0.5, sustain_sec=1.0)
    assert v.evaluate({"velocity": 0.7, "_timestamp": 0.0}) is None
    assert v.evaluate({"velocity": 0.7, "_timestamp": 0.5}) is None
    out = v.evaluate({"velocity": 0.7, "_timestamp": 1.5})
    assert out is not None and out.result is False


def test_ignores_record_missing_field():
    v = ThresholdVerdict("p", "velocity", ">", 0.5)
    assert v.evaluate({"other": 1.0}) is None
    assert v.evaluate("not a dict") is None


def test_rejects_unknown_op():
    with pytest.raises(ValueError):
        ThresholdVerdict("p", "v", "??", 1.0)


def test_supports_all_ops():
    for op, value, threshold, expected_breach in [
        (">", 1.0, 0.5, True),
        (">=", 0.5, 0.5, True),
        ("<", 0.0, 0.5, True),
        ("<=", 0.5, 0.5, True),
        ("==", 1.0, 1.0, True),
        ("!=", 1.0, 0.0, True),
    ]:
        v = ThresholdVerdict("p", "x", op, threshold)
        out = v.evaluate({"x": value, "_timestamp": 0.0})
        assert (out is not None) == expected_breach
