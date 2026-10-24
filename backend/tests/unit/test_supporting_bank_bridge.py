import copy
import uuid

import pytest

from app.modules.country_workflows.schemas import SourceInput
from app.modules.country_workflows.table_source import from_supporting_table


def request(**changes):
    return SourceInput(
        **{
            "evidence_version_id": uuid.UUID(int=1),
            "supporting_table_id": uuid.UUID(int=2),
            "supporting_scope_assessment": "Reviewed all rows as the independently identified BANK-1 population",
            "account_identifier": "BANK-1",
            "table_type": "transactions",
            "label": "Synthetic bank bridge",
            "expected_rows": 1,
            "control_totals": {"AED": "100.25"},
            **changes,
        }
    )


def body():
    return {
        "evidence_version_id": str(uuid.UUID(int=1)),
        "review_status": "REVIEWED",
        "table_kind": "bank",
        "row_count": 1,
        "rows": [
            {
                "id": "row-2",
                "source_row": 2,
                "date": "2026-06-30",
                "reference": "REF-1",
                "currency": "AED",
                "amount": "100.25",
                "counterparty": None,
                "account_code": "BANK-1",
            }
        ],
    }


def test_reviewed_table_reuse_preserves_normalized_values_and_original_row_identity():
    original = body()
    snapshot = copy.deepcopy(original)
    result = from_supporting_table(original, request())
    assert original == snapshot
    assert result["rows"][0]["supporting_source_row"] == 2
    assert result["rows"][0]["amount"] == "100.25"
    assert result["supporting_table_id"] == str(uuid.UUID(int=2))
    assert result["account_identity_verified"] is False
    assert "csv_mapping" not in result


@pytest.mark.parametrize(
    "changes",
    [
        {"review_status": "UNVERIFIED"},
        {"table_kind": "open-items"},
        {"evidence_version_id": str(uuid.UUID(int=3))},
        {"row_count": 2},
        {"rows": []},
    ],
)
def test_incompatible_or_incomplete_supporting_populations_are_rejected(changes):
    with pytest.raises(ValueError):
        from_supporting_table({**body(), **changes}, request())


@pytest.mark.parametrize(
    "changes",
    [
        {"account_identifier": "ANOTHER-ACCOUNT"},
        {"expected_rows": 2},
        {"control_totals": {"AED": "100.26"}},
        {"supporting_scope_assessment": ""},
        {"column_mapping": {"id": "Row"}},
        {"amount_derivation": "debit-positive", "debit_column": "Debit", "credit_column": "Credit"},
    ],
)
def test_explicit_scope_and_controls_cannot_be_overridden_or_bypassed(changes):
    with pytest.raises(ValueError):
        from_supporting_table(body(), request(**changes))


def open_body(**changes):
    value = body()
    value["table_kind"] = "open-items"
    value["rows"][0].update(
        {
            "counterparty": "PARTY-1",
            "document_date": "2026-06-10",
            "due_date": "2026-06-30",
            "open_amount": "100.25",
            "document_type": "invoice",
            "segment": "SYNTHETIC",
            **changes,
        }
    )
    return value


def open_request():
    return request(
        table_type="audit-open-items",
        supporting_side="receivable",
        supporting_balance_date="2026-06-30",
    )


def test_open_item_bridge_keeps_dates_classification_segment_and_reported_amount():
    result = from_supporting_table(open_body(), open_request())
    row = result["rows"][0]
    assert row["document_date"] == "2026-06-10" and row["due_date"] == "2026-06-30"
    assert row["balance_date"] == "2026-06-30" and row["side"] == "receivable"
    assert row["document_type"] == "invoice" and row["segment"] == "SYNTHETIC"
    assert row["supporting_reported_open_amount"] == "100.25"
    assert row["supporting_balance_date_basis"] == "DECLARED_SCOPE"
    assert row["supporting_original_balance_date"] is None


def test_payable_credit_negative_source_requires_an_explicit_sign_choice():
    original = open_body(open_amount="-100.25")
    with pytest.raises(ValueError):
        from_supporting_table(
            original, open_request().model_copy(update={"supporting_side": "payable"})
        )
    data = open_request().model_copy(
        update={"supporting_side": "payable", "supporting_amount_sign": "reverse-sign"}
    )
    result = from_supporting_table(original, data)
    assert result["rows"][0]["amount"] == "100.25"
    assert result["rows"][0]["supporting_reported_open_amount"] == "-100.25"
    assert result["supporting_amount_sign"] == "reverse-sign"


@pytest.mark.parametrize(
    "changes",
    [
        {"document_type": None},
        {"document_type": "unknown"},
        {"document_date": None},
        {"due_date": None},
        {"counterparty": None},
        {"balance_date": "2026-06-29"},
    ],
)
def test_open_items_never_infer_missing_classification_dates_or_party(changes):
    with pytest.raises(ValueError):
        from_supporting_table(open_body(**changes), open_request())


def test_open_item_balance_scope_is_mandatory():
    for changes in ({"supporting_side": None}, {"supporting_balance_date": None}):
        values = open_request().model_dump()
        with pytest.raises(ValueError):
            SourceInput.model_validate({**values, **changes})
    with pytest.raises(ValueError, match="supporting table selection"):
        SourceInput.model_validate({**open_request().model_dump(), "supporting_table_id": None})


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_reviewed_open_items_feed_the_existing_shared_ecl_engine(country):
    from decimal import Decimal

    from app.modules.country_workflows.calculations import calculate
    from app.modules.country_workflows.schemas import WorkflowInput
    from tests.unit.test_country_workflows import parsed
    from tests.unit.test_practice_audit_workflows import rate

    data = SourceInput.model_validate(
        {**open_request().model_dump(), "control_totals": {"AED": "80"}}
    )
    items = from_supporting_table(open_body(open_amount="80"), data)
    populations = {
        "items": items,
        "controls": parsed(
            "balance-controls",
            [
                {
                    "id": "GL",
                    "account": "BANK-1",
                    "side": "receivable",
                    "currency": "AED",
                    "as_of": "2026-06-30",
                    "amount": "80",
                }
            ],
        ),
        "rates": parsed("ecl-loss-rates", [rate()]),
    }
    request_data = WorkflowInput(
        workflow="receivables-ecl",
        source_ids={key: uuid.uuid4() for key in populations},
        as_of="2026-06-30",
        title="Synthetic reviewed-table ECL",
        rationale="Independent synthetic matrix and control inputs with reviewed open items",
    )
    result = calculate(request_data, country, populations)
    assert not result["blocked"] and result["exception_count"] == 0
    assert Decimal(result["total_ecl_by_currency"]["AED"]) == 8
