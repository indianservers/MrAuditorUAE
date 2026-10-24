import pytest

from app.modules.jurisdictions.ae.vat_errors import ErrorSchedule, calculate


def test_historical_differences_do_not_offset_period_errors_or_assert_a_filing_route():
    data = ErrorSchedule.model_validate({"periods": [
        {"period_start": "2026-01-01", "period_end": "2026-03-31", "filed_tax_due_aed": "100.10", "corrected_tax_due_aed": "120.11"},
        {"period_start": "2026-04-01", "period_end": "2026-06-30", "filed_tax_due_aed": "50", "corrected_tax_due_aed": "40"}],
        "correction_rule_review": "SYNTHETIC: applicable legal correction route remains pending professional approval"})
    result = calculate(data)
    assert result["gross_increases_aed"] == "20.01"
    assert result["gross_decreases_aed"] == "10"
    assert result["netting_permitted"] is None and result["submitted"] is False
    assert all(r["correction_workflow"] == "PROFESSIONAL_REVIEW_REQUIRED" for r in result["rows"])
    with pytest.raises(ValueError, match="overlapping"):
        calculate(data.model_copy(update={"periods": [data.periods[0],data.periods[0]]}))
