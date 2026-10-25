from datetime import date
from uuid import uuid4

import pytest

from app.modules.regulatory.conversion import ConversionInput, ExchangeRate, calculate


def quote(**changes):
    return {
        "id": "SYN-FX",
        "source_currency": "USD",
        "target_currency": "AED",
        "rate": "4",
        "coverage_start": "2026-01-01",
        "coverage_end": "2026-12-31",
        "rate_date": "2026-12-31",
        "method": "period-average",
        "source_url": "https://synthetic.example/quote",
        "source_evidence_version_id": str(uuid4()),
        "source_sha256": "a" * 64,
        "source_version": "SYNTHETIC-1",
        "applicability_review": "Synthetic arithmetic fixture only, not an actual or legally adopted rate",
        **changes,
    }


def control(**changes):
    return ConversionInput(
        source_event_id=uuid4(),
        rate_source_id=uuid4(),
        rate_row_id="SYN-FX",
        decimal_places=2,
        rounding="half-up",
        title="Synthetic assessed conversion",
        assessment="Synthetic explicit conversion basis and rounding verification",
        **{"target_amount": "400.80", **changes},
    )


def test_direct_rate_preserves_both_amounts_and_original_row():
    result = calculate(
        "100.20",
        "USD",
        date(2026, 1, 1),
        date(2026, 12, 31),
        {**quote(), "source_row": 2},
        control(),
    )
    assert result["source_amount"] == "100.20" and result["source_currency"] == "USD"
    assert result["converted_amount"] == "400.80" and result["target_currency"] == "AED"
    assert result["rate_source_row"] == 2


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"source_currency": "EUR"}, "direction"),
        ({"coverage_start": "2026-02-01"}, "complete reporting period"),
        ({"method": "closing"}, "reporting date exactly"),
    ],
)
def test_conversion_cannot_infer_rate_direction_or_missing_coverage(changes, error):
    with pytest.raises(ValueError, match=error):
        calculate(
            "100.20", "USD", date(2026, 1, 1), date(2026, 12, 31), quote(**changes), control()
        )


def test_closing_rate_and_independent_amount_control():
    q = quote(method="closing", coverage_start="2026-12-31")
    assert (
        calculate("100.20", "USD", date(2026, 1, 1), date(2026, 12, 31), q, control())[
            "converted_amount"
        ]
        == "400.80"
    )
    with pytest.raises(ValueError, match="control does not agree"):
        calculate(
            "100.20",
            "USD",
            date(2026, 1, 1),
            date(2026, 12, 31),
            q,
            control(target_amount="400.79"),
        )


@pytest.mark.parametrize(
    "mode,expected",
    [("half-up", "1.01"), ("half-even", "1.00"), ("towards-zero", "1.00"), ("floor", "1.00")],
)
def test_rounding_is_assessed_explicitly(mode, expected):
    data = ConversionInput(
        **{**control().model_dump(), "rounding": mode, "target_amount": expected}
    )
    result = calculate("1.005", "USD", date(2026, 1, 1), date(2026, 12, 31), quote(rate="1"), data)
    assert result["converted_amount"] == expected


@pytest.mark.parametrize(
    "changes",
    [
        {"rate": "0"},
        {"rate": "-1"},
        {"target_currency": "USD"},
        {"target_currency": "ZZZ"},
        {"rate_date": "2027-01-01"},
    ],
)
def test_invalid_quote_scope_rejects(changes):
    with pytest.raises(ValueError):
        ExchangeRate.model_validate(quote(**changes))
