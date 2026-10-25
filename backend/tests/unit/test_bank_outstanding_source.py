from copy import deepcopy

import pytest

from app.modules.country_workflows.bank_outstanding_source import (
    BankOutstandingSourceInput,
    source_rows,
)


def fixture():
    return (
        {
            "workflow": "bank-brs",
            "as_of": "2026-06-30",
            "parameters": {"account": "BANK-1", "currency": "AED"},
            "rows": [
                {
                    "id": "books:B1",
                    "source_id": "B1",
                    "side": "books",
                    "reference": "SYN-CHEQUE",
                    "currency": "AED",
                    "amount": "-100",
                    "cause": "UNPRESENTED_PAYMENT_CANDIDATE",
                    "auditor_status": "EXCEPTION_DOCUMENTED",
                }
            ],
        },
        {
            "rows": [
                {
                    "id": "B1",
                    "account": "BANK-1",
                    "currency": "AED",
                    "amount": "-100",
                    "date": "2026-06-20",
                    "reference": "SYN-CHEQUE",
                    "source_row": 3,
                }
            ]
        },
    )


def controls(**changes):
    return BankOutstandingSourceInput(
        **{
            "exception_ids": ["books:B1"],
            "expected_rows": 1,
            "signed_total": "-100",
            "label": "SYNTHETIC original BRS item",
            "assessment": "Original outstanding cheque retained for subsequent bank clearance",
            **changes,
        }
    )


def test_retained_original_and_brs_disposition_survive_without_mutation():
    body, books = fixture()
    original = deepcopy((body, books))
    rows, totals = source_rows(body, books, controls())
    assert (body, books) == original
    assert totals == {"AED": "-100"}
    assert rows[0]["date"] == "2026-06-20"
    assert rows[0]["source_book_evidence_row"] == 3
    assert rows[0]["source_candidate_cause"] == "UNPRESENTED_PAYMENT_CANDIDATE"
    assert rows[0]["source_exception_disposition"] == "EXCEPTION_DOCUMENTED"


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"exception_ids": ["missing"]}, "Only selected book-side"),
        ({"exception_ids": ["books:B1", "books:B1"]}, "Duplicate BRS"),
        ({"signed_total": "100"}, "control does not agree"),
        ({"expected_rows": 2}, "control does not agree"),
    ],
)
def test_independent_selection_and_controls(changes, error):
    with pytest.raises(ValueError, match=error):
        source_rows(*fixture(), controls(**changes))


def test_statement_side_or_changed_book_content_cannot_be_promoted():
    body, books = fixture()
    body["rows"][0]["side"] = "statement"
    with pytest.raises(ValueError, match="book-side"):
        source_rows(body, books, controls())
    body, books = fixture()
    books["rows"][0]["amount"] = "-99"
    with pytest.raises(ValueError, match="differs from its retained"):
        source_rows(body, books, controls())
