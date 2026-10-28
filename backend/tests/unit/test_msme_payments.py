"""Synthetic mechanics/boundary tests, not professional legal expected schedules."""

import uuid
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.msme_payments import due_dates
from app.modules.country_workflows.msme_schemas import MSMEInvoice
from app.modules.country_workflows.schemas import WorkflowInput
from tests.unit.test_country_workflows import parsed


def populations():
    return {
        "assessments": [
            {
                "id": "SCOPE",
                "buyer_id": "SYNTHETIC-BUYER",
                "supplier_id": "SYNTHETIC-SUPPLIER",
                "classification": "SMALL",
                "eligibility": "ELIGIBLE",
                "scope_start": "2026-01-01",
                "scope_end": "2026-12-31",
                "evidence_reference": "SYNTHETIC qualified supplier facts",
                "assessment": "Synthetic assessed applicability only, not a legal/client qualification",
            }
        ],
        "invoices": [
            {
                "id": "INV",
                "buyer_id": "SYNTHETIC-BUYER",
                "supplier_id": "SYNTHETIC-SUPPLIER",
                "reference": "SYNTHETIC-1",
                "invoice_date": "2026-01-01",
                "currency": "INR",
                "amount": "100",
                "assessment_id": "SCOPE",
                "delivery_date": "2026-01-01",
                "acceptance_evidence_reference": "SYNTHETIC delivery",
                "terms_written": False,
                "assessment": "Synthetic delivery and no-written-terms evidence assessed",
            }
        ],
        "bank": [
            {
                "id": "BANK",
                "account": "SYNTHETIC-ACCOUNT",
                "reference": "SYNTHETIC-BANK-1",
                "date": "2026-01-16",
                "currency": "INR",
                "amount": "-100",
            }
        ],
        "allocations": [
            {
                "id": "LINK",
                "item_id": "INV",
                "payment_id": "BANK",
                "currency": "INR",
                "amount": "100",
                "evidence_reference": "SYNTHETIC allocation",
                "rationale": "Synthetic invoice payment allocation assessed",
            }
        ],
    }


TYPES = {
    "assessments": "msme-supplier-assessments",
    "invoices": "msme-invoices",
    "bank": "transactions",
    "allocations": "item-allocations",
}


def config(**changes):
    return dict(
        workflow="india-msme-payment-timing",
        source_ids={r: str(uuid.uuid4()) for r in TYPES},
        msme_buyer_id="SYNTHETIC-BUYER",
        account="SYNTHETIC-ACCOUNT",
        currency="INR",
        as_of="2026-01-31",
        obligation_month_start="2026-01",
        obligation_month_end="2026-01",
        settlement_start="2026-01-01",
        bank_payment_sign="debit-negative",
        title="SYNTHETIC MSE timing",
        rationale="Synthetic acceptance and payment timing controls only",
        **changes,
    )


def run(rows=None, country="IN", **changes):
    rows = rows or populations()
    sources = {role: parsed(TYPES[role], population) for role, population in rows.items()}
    return calculate(WorkflowInput.model_validate({**config(), **changes}), country, sources)


def test_due_date_payment_boundary_and_source_identities_are_retained():
    result = run()
    row = result["rows"][0]
    assert row["acceptance_date"] == "2026-01-01" and row["due_date"] == "2026-01-16"
    assert row["late_paid_amount"] == row["overdue_unpaid_amount"] == "0"
    assert row["state"] == "MATCHED" and not result["blocked"]
    assert row["allocations"][0]["transaction_id"] == "BANK"
    assert row["retained_supplier_assessment"]["evidence_reference"].startswith("SYNTHETIC")
    assert result["statutory_calculation_qualified"] is False


@pytest.mark.parametrize(
    "delivery,expected",
    [("2026-01-31", "2026-02-15"), ("2028-02-20", "2028-03-06"), ("2026-12-25", "2027-01-09")],
)
def test_calendar_boundaries_without_invoice_date_substitution(delivery, expected):
    from datetime import date

    row = MSMEInvoice.model_validate(
        {**populations()["invoices"][0], "delivery_date": delivery}
    ).model_dump(mode="json")
    assert due_dates(row, date(2029, 1, 1))[1].isoformat() == expected


@pytest.mark.parametrize(
    "agreed,expected,warning",
    [
        ("2026-01-10", "2026-01-10", False),
        ("2026-02-15", "2026-02-15", False),
        ("2026-03-01", "2026-02-15", True),
    ],
)
def test_written_date_has_45_day_cap_without_silently_repairing_terms(agreed, expected, warning):
    rows = populations()
    rows["invoices"][0].update(
        terms_written=True,
        agreed_due_date=agreed,
        agreement_evidence_reference="SYNTHETIC written agreement",
    )
    row = run(rows)["rows"][0]
    assert row["due_date"] == expected
    assert ("WRITTEN_TERMS_EXCEED_45_DAY_CAP" in row["warnings"]) is warning
    if warning:
        assert "WRITTEN_TERMS_EXCEED_CAP" in row["reasons"]


def test_timely_objection_uses_actual_removal_and_late_objection_does_not_defer():
    rows = populations()
    rows["invoices"][0].update(
        written_objection_date="2026-01-16",
        objection_removed_date="2026-01-20",
        objection_evidence_reference="SYNTHETIC objection/removal",
    )
    row = run(rows)["rows"][0]
    assert row["acceptance_date"] == "2026-01-20" and row["due_date"] == "2026-02-04"
    rows["invoices"][0]["written_objection_date"] = "2026-01-17"
    row = run(rows)["rows"][0]
    assert row["acceptance_date"] == "2026-01-01" and row["due_date"] == "2026-01-16"
    assert row["warnings"] == ["LATE_OBJECTION_RETAINED_WITHOUT_ACCEPTANCE_DEFERRAL"]


@pytest.mark.parametrize(
    "fault",
    [
        "missing-qualification",
        "unresolved-qualification",
        "outside-qualification",
        "missing-delivery",
        "missing-delivery-evidence",
        "unresolved-objection",
        "missing-written-terms",
    ],
)
def test_unknown_facts_never_become_zero_lateness_or_compliance(fault):
    rows = populations()
    invoice = rows["invoices"][0]
    if fault == "missing-qualification":
        invoice["assessment_id"] = "ABSENT"
    elif fault == "unresolved-qualification":
        rows["assessments"][0]["eligibility"] = "UNRESOLVED"
    elif fault == "outside-qualification":
        rows["assessments"][0]["scope_start"] = "2026-01-02"
    elif fault == "missing-delivery":
        invoice["delivery_date"] = None
    elif fault == "missing-delivery-evidence":
        invoice["acceptance_evidence_reference"] = ""
    elif fault == "unresolved-objection":
        invoice.update(
            written_objection_date="2026-01-05",
            objection_evidence_reference="SYNTHETIC unresolved written objection",
        )
    else:
        invoice.update(terms_written=True)
    result = run(rows)
    row = result["rows"][0]
    assert result["blocked"] and row["due_date"] is None
    assert row["late_paid_amount"] is row["overdue_unpaid_amount"] is None
    assert result["unassessed_invoice_ids"] == ["INV"]


def test_partial_late_payment_and_overdue_principal_are_not_netted():
    rows = populations()
    rows["bank"][0]["date"] = "2026-01-17"
    rows["allocations"][0]["amount"] = "40"
    result = run(rows)
    row = result["rows"][0]
    assert row["late_paid_amount"] == "40" and row["overdue_unpaid_amount"] == "60"
    assert row["allocated_paid"] == "40" and row["unpaid_amount"] == "60"
    assert set(row["reasons"]) == {"LATE_PAYMENT", "OVERDUE_UNPAID"}
    assert not result["blocked"]  # Actual exceptions can be documented and reviewed.
    assert result["unallocated_bank_rows"][0]["unallocated_outflow"] == "60"


@pytest.mark.parametrize(
    "fault",
    [
        "buyer",
        "supplier",
        "invoice-overallocated",
        "bank-overallocated",
        "duplicate-link",
        "inflow",
        "reversal",
        "value-date",
        "wrong-currency",
        "outside-bank-window",
        "outside-invoice-window",
    ],
)
def test_cross_scope_or_invalid_cash_links_fail_closed(fault):
    rows = populations()
    if fault == "buyer":
        rows["invoices"][0]["buyer_id"] = "OTHER"
    elif fault == "supplier":
        rows["assessments"][0]["supplier_id"] = "OTHER"
    elif fault == "invoice-overallocated":
        rows["allocations"][0]["amount"] = "101"
    elif fault == "bank-overallocated":
        rows["bank"][0]["amount"] = "-99"
    elif fault == "duplicate-link":
        rows["allocations"].append({**rows["allocations"][0], "id": "DUP"})
    elif fault == "inflow":
        rows["bank"][0]["amount"] = "100"
    elif fault == "reversal":
        rows["bank"][0]["is_reversal"] = True
    elif fault == "value-date":
        rows["bank"][0].update(bank_date_basis="VALUE_DATE_FALLBACK", bank_value_date="2026-01-16")
    elif fault == "wrong-currency":
        rows["bank"][0]["currency"] = "AED"
    elif fault == "outside-bank-window":
        rows["bank"][0]["date"] = "2025-12-31"
    else:
        rows["invoices"][0]["invoice_date"] = "2025-12-31"
    with pytest.raises(ValueError):
        run(rows)


def test_country_exact_tolerances_and_literal_calendar_are_enforced():
    with pytest.raises(ValueError, match="unavailable"):
        run(country="AE")
    for changes in (
        {"tolerance": "0.01"},
        {"date_tolerance": 1},
        {"currency": "AED"},
        {"as_of": 0},
    ):
        with pytest.raises(ValidationError):
            WorkflowInput.model_validate({**config(), **changes})
    for value in (0, "2026-01-01T00:00:00"):
        with pytest.raises(ValidationError):
            MSMEInvoice.model_validate({**populations()["invoices"][0], "delivery_date": value})


def test_resolved_outside_scope_does_not_compute_an_mse_deadline():
    rows = deepcopy(populations())
    rows["assessments"][0].update(eligibility="INELIGIBLE", classification="MEDIUM")
    row = run(rows)["rows"][0]
    assert row["state"] == "NOT-APPLICABLE" and row["due_date"] is None
    assert row["late_paid_amount"] is None


def test_one_bank_debit_covers_distinct_invoices_without_cross_invoice_netting():
    rows = populations()
    rows["invoices"][0]["amount"] = "40"
    rows["invoices"].append(
        {**rows["invoices"][0], "id": "INV2", "reference": "SYNTHETIC-2", "amount": "60"}
    )
    rows["allocations"][0]["amount"] = "40"
    rows["allocations"].append(
        {**rows["allocations"][0], "id": "LINK2", "item_id": "INV2", "amount": "60"}
    )
    result = run(rows)
    assert [r["allocated_paid"] for r in result["rows"]] == ["40", "60"]
    assert all(r["unpaid_amount"] == "0" for r in result["rows"])
    assert result["unallocated_bank_rows"][0]["unallocated_outflow"] == "0"
    rows["allocations"][1]["amount"] = "61"
    with pytest.raises(ValueError, match="overallocated"):
        run(rows)


def test_split_payment_retains_on_time_and_late_amounts_separately():
    rows = populations()
    rows["bank"][0]["amount"] = "-40"
    rows["bank"].append(
        {
            **rows["bank"][0],
            "id": "BANK2",
            "reference": "SYNTHETIC-BANK-2",
            "date": "2026-01-17",
            "amount": "-60",
        }
    )
    rows["allocations"][0]["amount"] = "40"
    rows["allocations"].append(
        {**rows["allocations"][0], "id": "LINK2", "payment_id": "BANK2", "amount": "60"}
    )
    row = run(rows)["rows"][0]
    assert row["on_time_paid_amount"] == "40"
    assert row["late_paid_amount"] == "60" and row["unpaid_amount"] == "0"


def test_a_payment_before_objection_removal_is_retained_as_an_advance_not_a_tax_deduction():
    rows = populations()
    rows["invoices"][0].update(
        written_objection_date="2026-01-05",
        objection_removed_date="2026-01-20",
        objection_evidence_reference="SYNTHETIC removal",
    )
    result = run(rows)
    assert result["rows"][0]["pre_acceptance_payment_amount"] == "100"
    assert not result["statutory_calculation_qualified"]


def test_known_committed_books_cannot_be_relabelled_as_independent_bank_evidence():
    sources = {role: parsed(TYPES[role], records) for role, records in populations().items()}
    sources["bank"]["parser_version"] = "committed-ledger-1"
    with pytest.raises(ValueError, match="independent bank movement"):
        calculate(WorkflowInput.model_validate(config()), "IN", sources)


@pytest.mark.parametrize("native_format", ["camt053", "swift-mt940"])
def test_native_bank_credit_cannot_be_flipped_into_an_mse_payment(native_format):
    rows = populations()
    rows["bank"][0]["amount"] = "100"
    sources = {role: parsed(TYPES[role], records) for role, records in rows.items()}
    sources["bank"]["native_format"] = native_format
    with pytest.raises(ValueError, match="debit-negative"):
        calculate(
            WorkflowInput.model_validate({**config(), "bank_payment_sign": "debit-positive"}),
            "IN",
            sources,
        )


def test_reviewed_india_bank_account_link_uses_the_explicit_settlement_window():
    from app.modules.country_workflows.bank_binding import bind
    from tests.unit.test_bank_accounts import population
    from tests.unit.test_bank_accounts import run as account_review

    account_rows = population("IN")
    for records in account_rows.values():
        records[0]["account"] = "SYNTHETIC-ACCOUNT"
    review = account_review(
        account_rows, country="IN", as_of="2026-01-31", account="SYNTHETIC-ACCOUNT"
    )
    review["review_status"] = "REVIEWED"
    receipt = {
        "id": str(uuid.uuid4()),
        "root_id": str(uuid.uuid4()),
        "type": "event",
        "version": 2,
        "sha256": "a" * 64,
    }
    data = WorkflowInput.model_validate(
        {
            **config(),
            "bank_account_review_id": receipt["id"],
            "bank_account_scope_assessment": "Synthetic original account identity and complete January settlement window assessed",
        }
    )
    sources = {role: parsed(TYPES[role], records) for role, records in populations().items()}
    result = calculate(data, "IN", sources, bank_account_review=(review, receipt))
    assert result["bank_account_evidence"]["status"] == "REVIEWED_ACCOUNT_DOCUMENTS_LINKED"
    bad_review = deepcopy(review)
    bad_review["rows"][0]["valid_from"] = "2026-01-02"
    with pytest.raises(ValueError, match="entire financial review window"):
        bind(data, "IN", sources, bad_review, receipt)
