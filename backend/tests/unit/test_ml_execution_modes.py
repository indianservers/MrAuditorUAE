import pytest
from fastapi import HTTPException

from app.modules.ml.baselines import predict
from app.modules.ml.service import node


def row(**changes):
    return {
        "id": "R1",
        "journal": "J1",
        "client": "C1",
        "account": "A1",
        "date": "2026-12-30",
        "currency": "AED",
        "functional_currency": "AED",
        "debit": 1000.0,
        "credit": 0.0,
        **changes,
    }


def test_explicit_rules_and_diagnostic_modes_never_claim_trained_inference(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    output = predict([row()], "rules_baseline")
    assert output["execution_mode"] == "rules_baseline"
    assert output["predictions"][0]["score"] == 1
    assert not output["calibrated_probability"] and not output["production_validated"]
    diagnostic = predict([row()], "diagnostic_mock")
    assert diagnostic["predictions"][0]["score"] is None
    assert diagnostic["predictions"][0]["signal_category"] == "diagnostic_only"
    with pytest.raises(ValueError):
        predict([row()], "trained_model")


def test_constant_statistical_population_is_not_a_fraud_probability():
    output = predict([row(id=str(i)) for i in range(10)], "statistical_baseline")
    assert all(p["robust_log_amount_deviation"] is None for p in output["predictions"])
    assert all(p["score"] == 0 for p in output["predictions"])
    assert "zero is not clearance" in " ".join(output["limitations"])


@pytest.mark.parametrize(
    "changes",
    [
        {"debit": float("nan")},
        {"debit": -1},
        {"credit": True},
        {"date": "2026-02-30"},
        {"account": ""},
    ],
)
def test_baseline_input_failures_are_explicit(changes):
    with pytest.raises(ValueError):
        predict([row(**changes)], "rules_baseline")


def test_missing_model_never_silently_runs_a_baseline():
    with pytest.raises(ValueError, match="ML_MODEL_UNAVAILABLE"):
        node("infer", rows=[row()])


def test_local_child_worker_admission_is_bounded():
    from app.modules.ml.service import _NODE_SLOTS

    assert _NODE_SLOTS.acquire(blocking=False)
    assert _NODE_SLOTS.acquire(blocking=False)
    try:
        with pytest.raises(HTTPException) as failure:
            node("infer", rows=[row()])
        assert failure.value.status_code == 429
    finally:
        _NODE_SLOTS.release()
        _NODE_SLOTS.release()
