from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.ml.contracts import FinancialPopulation, JournalHeader, chronological_splits
from app.modules.ml.fixtures import SECTORS, financial_fixture
from app.modules.ml.foundation import prepare_reviewed, review_baseline


def population():
    return dict(
        tenant_id="tenant",
        entity_id="entity",
        source_system="SYNTHETIC",
        period_start="2026-01-01",
        period_end="2026-12-31",
        functional_currency="AED",
        usage_permission="synthetic_only",
        expected_line_count=2,
        accounts=[dict(id="a", code="100")],
        journals=[dict(id="j", posting_date="2026-01-01", complete=True)],
        lines=[
            dict(id="1", journal_id="j", account_id="a", debit="0.1", credit="0", currency="AED"),
            dict(id="2", journal_id="j", account_id="a", debit="0", credit="0.1", currency="AED"),
        ],
    )


def test_decimal_balance_and_completeness():
    data = population()
    model = FinancialPopulation.model_validate(data)
    assert model.lines[0].debit == Decimal("0.1")
    assert model.manifest()["production_quality_evidence"] is False
    data["lines"][1]["credit"] = "0.10000000000000000001"
    with pytest.raises(ValidationError, match="unbalanced"):
        FinancialPopulation.model_validate(data)
    data["journals"][0]["complete"] = False
    assert FinancialPopulation.model_validate(data).manifest()["incomplete_journals"] == 1


def test_connected_reversals_move_to_latest_partition():
    journals = [
        JournalHeader(id="a", posting_date=date(2026, 1, 1)),
        JournalHeader(id="b", posting_date=date(2026, 6, 1), reversal_of="a"),
        JournalHeader(id="c", posting_date=date(2026, 12, 1)),
    ]
    result = chronological_splits(journals, date(2026, 3, 31), date(2026, 9, 30))
    assert result == {"a": "validation", "b": "validation", "c": "test"}


@pytest.mark.parametrize("field,value", [("expected_line_count", 3), ("period_end", "2025-01-01")])
def test_invalid_source_contract(field, value):
    data = population()
    data[field] = value
    with pytest.raises(ValidationError):
        FinancialPopulation.model_validate(data)


def test_reviewed_dataset_keeps_decimal_amounts_and_rejects_unknown_labels():
    rows = [
        dict(
            id=str(i),
            journal=str(i),
            account="a",
            date=f"2026-{month}-01",
            debit="0.100000000000000001",
            credit="0",
            currency="AED",
        )
        for i, month in enumerate(["01", "06", "12"])
    ]
    data, manifest = prepare_reviewed(
        rows,
        "journal-type",
        {str(i): "sales" for i in range(3)},
        date(2026, 3, 31),
        date(2026, 9, 30),
    )
    assert data["rows"][0]["debit"] == "0.100000000000000001"
    assert [r["split"] for r in data["rows"]] == ["train", "validation", "test"]
    assert manifest["generalization_claim"] is None
    partial, partial_manifest = prepare_reviewed(
        rows, "journal-type", {"0": "sales"}, date(2026, 3, 31), date(2026, 9, 30)
    )
    assert partial_manifest["training_eligible"] is False
    complete, complete_manifest = prepare_reviewed(
        partial["rows"],
        "journal-type",
        {"1": "sales", "2": "sales"},
        date(2026, 3, 31),
        date(2026, 9, 30),
    )
    assert complete_manifest["training_eligible"] is True
    assert complete["rows"][0]["target"] == "sales"
    with pytest.raises(ValueError, match="reviewed taxonomy"):
        prepare_reviewed(
            rows,
            "journal-type",
            {str(i): "suspicious" for i in range(3)},
            date(2026, 3, 31),
            date(2026, 9, 30),
        )


def test_ranking_baseline_is_explicit_and_fits_only_earlier_journals():
    rows = [
        dict(
            id=str(i),
            journal=str(i),
            account="a",
            date="2026-01-01" if i < 10 else "2026-12-01",
            debit="100" if i < 10 else "999999",
            credit="0",
            currency="AED",
        )
        for i in range(11)
    ]
    weights = {"amount": 1, "rare_pair": 1, "manual": 0, "outside_calendar": 0}
    result = review_baseline(rows, date(2026, 6, 30), weights, [0, 1, 2, 3, 4])
    assert result["execution_mode"] == "statistical_baseline"
    assert result["quality_metrics"] is None
    assert len(result["predictions"]) == 1
    assert result["predictions"][0]["financial_exposure"]["gross_debits"] == "999999"
    assert result["predictions"][0]["score"] > 0


def test_six_synthetic_sectors_have_decimal_fx_balanced_complete_journals_and_missing_fields():
    for sector in SECTORS:
        fixture = financial_fixture(sector)
        assert fixture.manifest()["usage_permission"] == "synthetic_only"
        assert fixture.manifest()["incomplete_journals"] == 1
        assert any(line.currency == "USD" for line in fixture.lines)
        assert fixture.journals[-1].reversal_of == fixture.journals[0].id
