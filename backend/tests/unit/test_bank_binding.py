"""Reviewed account scope bridges ledger codes and original bank identifiers."""

import uuid
from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.bank_binding import bind
from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import WorkflowInput
from tests.unit.native_source_examples import CAMT, MT940, iban
from tests.unit.test_bank_accounts import run as account_review
from tests.unit.test_country_workflows import parsed
from tests.unit.test_native_workflow_sources import options


def example(file_format="camt053"):
    receipt = {
        "id": str(uuid.uuid4()),
        "root_id": str(uuid.uuid4()),
        "type": "event",
        "version": 2,
        "sha256": "a" * 64,
    }
    review = account_review()
    review["review_status"] = "REVIEWED"
    book_rows = [
        dict(
            id="B1",
            account="SYN-BANK",
            reference="PAY-1",
            date="2026-06-01",
            currency="AED",
            amount="100",
        ),
        dict(
            id="B2",
            account="SYN-BANK",
            reference="FEE",
            date="2026-06-02",
            currency="AED",
            amount="-5",
        ),
    ]
    sources = {
        "books": parsed("transactions", book_rows),
        "statement": parse_native(
            (CAMT if file_format == "camt053" else MT940).replace(b"BANK-1", iban().encode()),
            options(file_format),
            "AE",
            "SYNTHETIC.xml" if file_format == "camt053" else "SYNTHETIC.sta",
        ),
    }
    data = WorkflowInput(
        workflow="bank-brs",
        source_ids={role: uuid.uuid4() for role in sources},
        as_of="2026-06-30",
        account="SYN-BANK",
        currency="AED",
        title="Synthetic scoped bank reconciliation",
        rationale="Independent synthetic account mapping and period assessment",
        book_opening="0",
        book_closing="95",
        statement_opening="0",
        statement_closing="95",
        bank_account_review_id=receipt["id"],
        bank_account_scope_assessment="Independent ledger label to retained bank number and full June window assessment",
    )
    return data, sources, review, receipt


@pytest.mark.parametrize("file_format", ["camt053", "swift-mt940"])
def test_native_account_maps_only_after_review_without_changing_original_evidence_or_balances(
    file_format,
):
    data, sources, review, receipt = example(file_format)
    original = deepcopy(sources)
    with pytest.raises(ValueError, match="original native"):
        calculate(data, "AE", sources)
    result = calculate(data, "AE", sources, bank_account_review=(review, receipt))
    assert not result["blocked"] and result["exception_count"] == 0
    assert sources == original
    link = result["bank_account_evidence"]
    assert link["original_bank_source_account"] == iban()
    assert link["account"] == "SYN-BANK" and link["account_label_mapping_applied"]
    assert link["source_account_binding"] == "NATIVE_ACCOUNT_NUMBER_AGREES_TO_REVIEWED_DOCUMENTS"
    assert sources["statement"]["native_metadata"]["account"] == iban()
    assert link["review_receipt"] == receipt
    assert link["window_start"] == "2026-06-01" and link["window_end"] == "2026-06-30"
    assert link["bank_authentication_status"] == "NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON"


@pytest.mark.parametrize(
    "change,message",
    [
        ("unreviewed", "independently reviewed"),
        ("blocked", "independently reviewed"),
        ("account", "account, currency"),
        ("currency", "account, currency"),
        ("country", "account, currency"),
        ("asof", "window end"),
        ("start", "entire financial"),
        ("end", "entire financial"),
        ("missing", "all three"),
        ("native-account", "Native statement account"),
        ("wrong-request", "workflow request"),
        ("contract", "supported bank account"),
    ],
)
def test_unqualified_or_wrong_scope_cannot_authorize_an_account_alias(change, message):
    data, sources, review, receipt = example()
    if change == "unreviewed":
        review["review_status"] = "UNVERIFIED"
    elif change == "blocked":
        review["blocked"] = True
    elif change == "account":
        review["bank_account_scope"]["account"] = "OTHER"
    elif change == "currency":
        review["bank_account_scope"]["currency"] = "USD"
    elif change == "country":
        review["bank_account_scope"]["owner_country"] = "IN"
    elif change == "asof":
        review["as_of"] = "2026-06-29"
    elif change == "start":
        review["rows"][0]["valid_from"] = "2026-06-02"
    elif change == "end":
        review["rows"][1]["valid_through"] = "2026-06-29"
    elif change == "missing":
        review["rows"].pop()
    elif change == "native-account":
        review["rows"][2]["account_number"] = "OTHER"
    elif change == "wrong-request":
        receipt["id"] = str(uuid.uuid4())
    else:
        review["bank_account_contract"] = "unsupported"
    with pytest.raises(ValueError, match=message):
        bind(data, "AE", sources, review, receipt)


def test_canonical_account_labels_are_explicitly_distinct_from_number_binding():
    data, sources, review, receipt = example()
    rows = deepcopy(sources["books"]["rows"])
    sources["statement"] = parsed("transactions", [{**row, "id": "S-" + row["id"]} for row in rows])
    result = calculate(data, "AE", sources, bank_account_review=(review, receipt))
    assert (
        result["bank_account_evidence"]["source_account_binding"]
        == "DECLARED_LEDGER_ACCOUNT_LABEL_ONLY"
    )
    assert not result["bank_account_evidence"]["account_label_mapping_applied"]
    for row in sources["statement"]["rows"]:
        row["account"] = iban()
    result = calculate(data, "AE", sources, bank_account_review=(review, receipt))
    assert result["bank_account_evidence"]["account_label_mapping_applied"]
    sources["statement"]["rows"][1]["account"] = "OTHER"
    with pytest.raises(ValueError, match="cannot merge"):
        calculate(data, "AE", sources, bank_account_review=(review, receipt))


def test_a_requested_link_cannot_be_self_certified_by_the_pure_calculator():
    data, sources, review, receipt = example()
    sources["statement"] = parsed(
        "transactions", [{**row, "id": "S-" + row["id"]} for row in sources["books"]["rows"]]
    )
    pending = calculate(data, "AE", sources)
    assert pending["bank_account_evidence"]["status"] == "LINK_REQUESTED_NOT_VERIFIED"
    assert "Verify the requested" in approval_error(pending)
    unlinked = calculate(
        data.model_copy(
            update={"bank_account_review_id": None, "bank_account_scope_assessment": ""}
        ),
        "AE",
        sources,
    )
    assert unlinked["bank_account_evidence"]["status"] == "NOT_LINKED_ARITHMETIC_SCOPE_ONLY"


def test_link_parameters_require_supported_workflow_and_assessment():
    data, _, _, _ = example()
    for changes in (
        {"bank_account_scope_assessment": " "},
        {"workflow": "controls", "source_ids": {"checks": str(uuid.uuid4())}},
        {"bank_account_review_id": None},
    ):
        with pytest.raises(ValidationError):
            WorkflowInput.model_validate({**data.model_dump(mode="json"), **changes})


@pytest.mark.parametrize("workflow", ["bank-subsequent-clearance", "obligation-bank-allocations"])
def test_account_mapping_is_reused_for_clearance_and_obligation_settlement(workflow):
    from tests.unit.test_bank_clearance import population as clearance_rows
    from tests.unit.test_dues_allocations import example as dues_rows
    from tests.unit.test_dues_allocations import parameters as dues_parameters

    _, _, review, receipt = example()
    review["bank_account_scope"]["account"] = "BANK-1"
    for row in review["rows"]:
        row["account"] = "BANK-1"
    if workflow == "bank-subsequent-clearance":
        populations = clearance_rows()
        populations["statement"][0]["account"] = iban()
        types = {
            "outstanding": "bank-outstanding",
            "statement": "transactions",
            "allocations": "bank-clearances",
        }
        changes = dict(
            workflow=workflow,
            source_ids={role: uuid.uuid4() for role in populations},
            account="BANK-1",
            currency="AED",
            as_of="2026-06-30",
            review_through="2026-08-31",
            title="Synthetic linked bank clearance",
            rationale="Independent bank scope across original item and subsequent period",
        )
        review["as_of"] = "2026-08-31"
    else:
        populations = dues_rows()
        for row in populations["bank"]:
            row["account"] = iban()
        types = {
            "expected": "obligations",
            "reported": "obligations",
            "bank": "transactions",
            "allocations": "obligation-allocations",
        }
        changes = dues_parameters(currency="AED")
    data = WorkflowInput(
        **{
            **changes,
            "bank_account_review_id": receipt["id"],
            "bank_account_scope_assessment": "Independently assessed bank number and complete financial window",
        }
    )
    sources = {role: parsed(types[role], rows) for role, rows in populations.items()}
    result = calculate(data, "AE", sources, bank_account_review=(review, receipt))
    assert result["bank_account_evidence"]["account_label_mapping_applied"]
    assert result["bank_account_evidence"]["bank_source_role"] == (
        "bank" if workflow == "obligation-bank-allocations" else "statement"
    )
    assert result["bank_account_evidence"]["window_end"] == (
        "2026-08-31" if workflow == "bank-subsequent-clearance" else "2026-06-30"
    )
    assert (
        sources[result["bank_account_evidence"]["bank_source_role"]]["rows"][0]["account"] == iban()
    )


def test_account_alias_does_not_override_native_financial_controls():
    data, sources, review, receipt = example()
    wrong = data.model_copy(update={"statement_closing": Decimal("96")})
    with pytest.raises(ValueError, match="original native"):
        calculate(wrong, "AE", sources, bank_account_review=(review, receipt))


@pytest.mark.parametrize(
    "workflow,expected_start",
    [("obligation-bank-allocations", "2026-06-01"), ("bank-subsequent-clearance", "2026-06-20")],
)
def test_explicit_settlement_and_clearance_windows_do_not_expand_to_unrelated_header_dates(
    workflow, expected_start
):
    from datetime import date
    from types import SimpleNamespace

    from app.modules.country_workflows.bank_binding import financial_window

    data = SimpleNamespace(
        workflow=workflow,
        settlement_start=date(2026, 6, 1),
        as_of=date(2026, 6, 30),
        review_through=date(2026, 8, 31),
    )
    sources = {
        "bank": {
            "rows": [
                {"date": "2026-07-02" if workflow == "bank-subsequent-clearance" else "2026-06-15"}
            ],
            "native_metadata": {"from": "2026-01-01"},
        }
    }
    if workflow == "bank-subsequent-clearance":
        sources["outstanding"] = {"rows": [{"date": "2026-06-20"}]}
    start, end = financial_window(data, sources)
    assert start.isoformat() == expected_start
    assert end.isoformat() == (
        "2026-08-31" if workflow == "bank-subsequent-clearance" else "2026-06-30"
    )
