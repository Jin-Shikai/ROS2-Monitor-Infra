from custom.threshold import ThresholdVerdict


def test_fires_violation_on_breach():
    out = ThresholdVerdict(threshold=0.5).evaluate({"speed": 0.7, "_timestamp": 1.0})
    assert out is not None
    assert out.result is False
    assert out.property_id == "speed"
    assert out.details == {"field": "speed", "threshold": 0.5, "value": 0.7}


def test_uses_property_id_from_dsl_record():
    out = ThresholdVerdict(threshold=0.5).evaluate({
        "relative_speed": 0.7,
        "_property_id": "fleet_relative_speed",
        "_timestamp": 1.0,
    })
    assert out is not None
    assert out.property_id == "fleet_relative_speed"


def test_silent_when_under_threshold():
    assert ThresholdVerdict(threshold=0.5).evaluate({"speed": 0.2}) is None


def test_emits_only_on_state_transition():
    verdict = ThresholdVerdict(threshold=0.5)
    first = verdict.evaluate({"speed": 0.7, "_timestamp": 1.0})
    second = verdict.evaluate({"speed": 0.8, "_timestamp": 1.1})
    third = verdict.evaluate({"speed": 0.2, "_timestamp": 1.2})
    fourth = verdict.evaluate({"speed": 0.1, "_timestamp": 1.3})
    assert first is not None and first.result is False
    assert second is None
    assert third is not None and third.result is True
    assert fourth is None


def test_ignores_unusable_records():
    verdict = ThresholdVerdict(threshold=0.5)
    assert verdict.evaluate({"flag": True}) is None
    assert verdict.evaluate("not a dict") is None
