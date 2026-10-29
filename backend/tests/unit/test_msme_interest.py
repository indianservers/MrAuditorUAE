"""Synthetic assessed populations and authored interest expectations, not client qualification."""

from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.msme_interest import calculate
from tests.unit.test_msme_payments import populations


def fixture():
    tables = populations()
    tables["invoices"][0].update(
        invoice_date="2026-05-16", delivery_date="2026-05-16", amount="36500"
    )
    tables["bank"][0].update(date="2026-07-01", amount="-1000")
    tables["allocations"] = []
    parties = dict(
        buyer_id="SYNTHETIC-BUYER",
        supplier_id="SYNTHETIC-SUPPLIER",
        invoice_id="INV",
        currency="INR",
    )
    evidence = dict(
        source_url="https://synthetic.example/assessed-interest",
        source_evidence_version_id="00000000-0000-4000-8000-000000000001",
        source_sha256="a" * 64,
        source_version="Synthetic reviewed conventions, not operative law",
        evidence_reference="SYNTHETIC assessed support",
        applicability_review="Synthetic assessed principal and accrual interpretation only",
    )
    tables.update(
        interest_policies=[
            dict(
                id="POLICY",
                **parties,
                **evidence,
                eligible=True,
                amount="36500",
                effective_from="2026-01-01",
                effective_to="2026-12-31",
                history_from="2026-05-16",
                history_assessment="Independent full invoice and payment history assessment",
                interest_start="2026-06-01",
                start_basis="TIMING_DUE_PLUS_ONE",
                start_assessment="Synthetic due date and next-day accrual start assessed",
                rate_group="SYNTHETIC-RBI",
                bank_rate_multiplier="3",
                rest_basis="CALENDAR_MONTH_END",
                day_basis="ACT_365_FIXED",
                event_timing="END_OF_DAY",
                rest_rounding="ROUND_EACH_REST",
                rounding="HALF_UP",
            )
        ],
        bank_rates=[
            dict(
                id="RATE",
                **evidence,
                rate_group="SYNTHETIC-RBI",
                rate_kind="RBI_BANK_RATE",
                annual_rate="0.01",
                effective_from="2026-01-01",
                effective_to="2026-12-31",
            )
        ],
        principal_changes=[],
        interest_allocations=[],
        reported=[
            dict(
                id="REPORTED",
                **parties,
                as_of="2026-07-31",
                amount="183.23",
                evidence_reference="SYNTHETIC independently retained closing balance",
            )
        ],
    )
    data = SimpleNamespace(
        msme_buyer_id=parties["buyer_id"],
        account="SYNTHETIC-ACCOUNT",
        currency="INR",
        as_of=date(2026, 7, 31),
        obligation_month_start="2026-05",
        obligation_month_end="2026-05",
        settlement_start=date(2026, 5, 16),
        bank_payment_sign="debit-negative",
        tolerance=0,
        date_tolerance=0,
    )
    return data, tables


def close_june(data, tables, expected):
    data.as_of = date(2026, 6, 30)
    tables["bank"][0]["date"] = "2026-06-30"
    tables["reported"][0].update(as_of="2026-06-30", amount=expected)


def partial_principal(data, tables):
    close_june(data, tables, "37.81")
    tables["bank"][0].update(date="2026-06-16", amount="-20000")
    tables["allocations"] = [
        dict(
            id="LINK",
            item_id="INV",
            payment_id="BANK",
            currency="INR",
            amount="20000",
            evidence_reference="SYNTHETIC original bank advice",
            rationale="Assessed original gross invoice principal payment",
        )
    ]
    tables["interest_policies"][0]["amount"] = "20000"
    tables["principal_changes"] = [
        dict(
            id="PORTION",
            **{
                key: tables["interest_policies"][0][key]
                for key in ("buyer_id", "supplier_id", "invoice_id", "currency")
            },
            mode="BANK_PRINCIPAL_PORTION",
            amount="10000",
            principal_allocation_id="LINK",
            evidence_reference="SYNTHETIC assessed taxable principal portion",
            rationale="Independent appropriation to the assessed interest principal",
        )
    ]


def interest_payment(tables, amount="90", bucket="UNCAPITALIZED_INTEREST"):
    return dict(
        id="INTEREST-PAYMENT",
        **{
            key: tables["interest_policies"][0][key]
            for key in ("buyer_id", "supplier_id", "invoice_id", "currency")
        },
        payment_id="BANK",
        amount=amount,
        bucket=bucket,
        evidence_reference="SYNTHETIC bank interest appropriation",
        rationale="Independent payment advice and unpaid interest bucket",
    )


def settled_fixture():
    data, tables = fixture()
    tables["bank"][0].update(date="2026-07-31", amount="-1000")
    tables["allocations"] = [
        dict(
            id="LINK",
            item_id="INV",
            payment_id="BANK",
            currency="INR",
            amount="900",
            evidence_reference="SYNTHETIC bank principal advice",
            rationale="Independent original gross principal allocation",
        )
    ]
    parties = {
        key: tables["interest_policies"][0][key]
        for key in ("buyer_id", "supplier_id", "invoice_id", "currency")
    }
    tables["principal_changes"] = [
        dict(
            id="PORTION",
            **parties,
            mode="BANK_PRINCIPAL_PORTION",
            amount="900",
            principal_allocation_id="LINK",
            evidence_reference="SYNTHETIC principal portion",
            rationale="Independent full principal portion, not an inferred allocation",
        )
    ]
    tables["interest_allocations"] = [interest_payment(tables, bucket="CAPITALIZED_INTEREST")]
    tables["reported"][0]["amount"] = "93.23"
    return data, tables


def test_reuses_original_timing_without_clearing_its_principal_breach_or_mutating_sources():
    data, tables = fixture()
    original = deepcopy(tables)
    result = calculate(data, tables)
    assert (
        not result["blocked"]
        and result["expected_total"] == "183.23"
        and result["exception_count"] == 0
    )
    assert result["principal_timing_exception_count"] == 1
    assert result["rows"][0]["timing_reasons"] == ["OVERDUE_UNPAID"]
    assert len(result["rows"][0]["monthly_rests"]) == 2 and tables == original


def test_partial_gross_payment_uses_explicit_interest_principal_portion_not_a_proportion():
    data, tables = fixture()
    partial_principal(data, tables)
    row = calculate(data, tables)["rows"][0]
    assert row["expected_amount"] == "37.81" and row["principal_remaining"] == "10000"
    assert row["unpaid_amount"] == "16500" and row["assessed_interest_principal"] == "20000"


def test_missing_principal_portion_is_unresolved_not_an_assumed_zero():
    data, tables = fixture()
    partial_principal(data, tables)
    tables["principal_changes"] = []
    row = calculate(data, tables)["rows"][0]
    assert row["state"] == "PRINCIPAL_PORTIONS_MISSING" and row["expected_amount"] is None


def test_interest_cannot_reuse_gross_principal_cash_even_when_its_assessed_portion_is_smaller():
    data, tables = fixture()
    partial_principal(data, tables)
    tables["interest_allocations"] = [interest_payment(tables, "1")]
    with pytest.raises(ValueError, match="Combined gross principal and interest"):
        calculate(data, tables)


def test_independent_principal_and_interest_shares_fit_one_bank_outflow():
    data, tables = fixture()
    close_june(data, tables, "0")
    tables["allocations"] = [
        dict(
            id="LINK",
            item_id="INV",
            payment_id="BANK",
            currency="INR",
            amount="900",
            evidence_reference="SYNTHETIC gross principal",
            rationale="Independent principal allocation from original advice",
        )
    ]
    tables["principal_changes"] = [
        dict(
            id="PORTION",
            **{
                key: tables["interest_policies"][0][key]
                for key in ("buyer_id", "supplier_id", "invoice_id", "currency")
            },
            mode="BANK_PRINCIPAL_PORTION",
            amount="900",
            principal_allocation_id="LINK",
            evidence_reference="SYNTHETIC full principal portion",
            rationale="Independent full interest principal portion allocation",
        )
    ]
    tables["interest_allocations"] = [interest_payment(tables)]
    row = calculate(data, tables)["rows"][0]
    assert (
        row["expected_amount"] == "0.00"
        and row["interest_cash_paid"] == "90"
        and row["principal_remaining"] == "35600"
    )


def test_documented_non_cash_reduction_has_its_own_date_and_support():
    data, tables = fixture()
    close_june(data, tables, "69")
    policy = tables["interest_policies"][0]
    tables["principal_changes"] = [
        dict(
            id="CREDIT",
            **{
                key: policy[key]
                for key in (
                    "buyer_id",
                    "supplier_id",
                    "invoice_id",
                    "currency",
                    "source_url",
                    "source_evidence_version_id",
                    "source_sha256",
                    "source_version",
                    "applicability_review",
                )
            },
            mode="DOCUMENTED_PRINCIPAL_REDUCTION",
            amount="18250",
            day="2026-06-16",
            evidence_reference="SYNTHETIC dated credit assessment",
            rationale="Retained independent dated non-cash principal reduction",
        )
    ]
    row = calculate(data, tables)["rows"][0]
    assert row["expected_amount"] == "69.00" and row["interest_cash_paid"] == "0"
    assert row["balance_events"][0]["source_record"]["mode"] == "DOCUMENTED_PRINCIPAL_REDUCTION"


@pytest.mark.parametrize("field,value", [("source_sha256", None), ("day", None), ("amount", "0")])
def test_non_cash_reduction_cannot_lose_its_independent_evidence_or_date(field, value):
    data, tables = fixture()
    policy = tables["interest_policies"][0]
    row = dict(
        id="CREDIT",
        **{
            key: policy[key]
            for key in (
                "buyer_id",
                "supplier_id",
                "invoice_id",
                "currency",
                "source_url",
                "source_evidence_version_id",
                "source_sha256",
                "source_version",
                "applicability_review",
            )
        },
        mode="DOCUMENTED_PRINCIPAL_REDUCTION",
        amount="10",
        day="2026-06-16",
        evidence_reference="SYNTHETIC credit assessment",
        rationale="Retained independent non-cash reduction",
        **{},
    )
    row[field] = value
    tables["principal_changes"] = [row]
    with pytest.raises(ValidationError):
        calculate(data, tables)


def test_bank_portion_cannot_replace_the_original_booking_date():
    data, tables = fixture()
    partial_principal(data, tables)
    tables["principal_changes"][0]["day"] = "2026-05-16"
    with pytest.raises(ValidationError, match="derives its date"):
        calculate(data, tables)


def test_missing_rate_does_not_become_zero_expected_interest():
    data, tables = fixture()
    tables["bank_rates"] = []
    result = calculate(data, tables)
    assert result["blocked"] and result["rows"][0]["expected_amount"] is None
    assert result["rows"][0]["state"] == "BANK_RATE_COVERAGE_MISSING:2026-06-01"


def test_overlapping_rate_versions_are_not_selected_by_order():
    data, tables = fixture()
    tables["bank_rates"].append(
        {**tables["bank_rates"][0], "id": "OTHER", "effective_from": "2026-06-16"}
    )
    with pytest.raises(ValueError, match="Competing bank-rate"):
        calculate(data, tables)


@pytest.mark.parametrize(
    "change", [{"history_from": "2026-05-17"}, {"effective_from": "2026-06-16"}]
)
def test_incomplete_history_or_policy_scope_is_unresolved(change):
    data, tables = fixture()
    tables["interest_policies"][0].update(change)
    result = calculate(data, tables)
    assert result["blocked"] and result["rows"][0]["expected_amount"] is None


def test_unresolved_supplier_facts_cannot_be_overridden_to_zero_by_an_interest_policy():
    data, tables = fixture()
    tables["assessments"][0]["eligibility"] = "UNRESOLVED"
    result = calculate(data, tables)
    assert result["blocked"] and result["rows"][0]["state"] == "TIMING_OR_ELIGIBILITY_UNRESOLVED"


def test_missing_acceptance_cannot_be_replaced_by_an_interest_start_assertion():
    data, tables = fixture()
    tables["invoices"][0]["delivery_date"] = None
    assert calculate(data, tables)["rows"][0]["expected_amount"] is None


def test_reported_interest_has_its_own_exact_cutoff_and_party_scope():
    data, tables = fixture()
    tables["reported"][0]["as_of"] = "2026-06-30"
    with pytest.raises(ValueError, match="at this cutoff"):
        calculate(data, tables)
    tables["reported"][0].update(as_of="2026-07-31", supplier_id="OTHER")
    with pytest.raises(ValueError, match="different invoice"):
        calculate(data, tables)


def test_missing_observation_is_absent_not_zero_while_expected_is_resolved():
    data, tables = fixture()
    tables["reported"] = []
    row = calculate(data, tables)["rows"][0]
    assert (
        row["expected_amount"] == "183.23"
        and row["reported_amount"] is None
        and row["difference"] is None
    )


def test_timing_start_cannot_be_silently_moved_to_avoid_interest():
    data, tables = fixture()
    tables["interest_policies"][0]["interest_start"] = "2026-08-01"
    with pytest.raises(ValueError, match="immediately follow"):
        calculate(data, tables)


def test_separately_assessed_future_start_is_explicit_and_retained():
    data, tables = fixture()
    tables["interest_policies"][0].update(
        interest_start="2026-08-01",
        start_basis="SEPARATELY_ASSESSED_START",
        start_assessment="Separate retained judgement date assessed, not automatically inferred",
    )
    row = calculate(data, tables)["rows"][0]
    assert (
        row["expected_amount"] == "0.00"
        and row["interest_policy"]["start_basis"] == "SEPARATELY_ASSESSED_START"
    )


def test_trace_limit_rejects_large_scope_instead_of_truncating_financial_records(monkeypatch):
    from app.modules.country_workflows import msme_interest

    data, tables = fixture()
    monkeypatch.setattr(msme_interest, "TRACE_LIMIT", 1)
    with pytest.raises(ValueError, match="smaller populations"):
        calculate(data, tables)


def test_nine_original_source_roles_and_country_request_bounds():
    from uuid import UUID

    from app.modules.country_workflows.calculations import calculate as workflow
    from app.modules.country_workflows.msme_interest_schemas import ROLES
    from app.modules.country_workflows.schemas import ROW_TYPES, WorkflowInput
    from tests.unit.test_country_workflows import parsed

    data, tables = settled_fixture()
    sources = {
        role: parsed(
            table_type,
            [
                ROW_TYPES[table_type].model_validate(row).model_dump(mode="json")
                for row in tables[role]
            ],
        )
        for role, table_type in ROLES.items()
    }
    params = WorkflowInput(
        workflow="india-msme-interest",
        source_ids={role: UUID(int=i + 1) for i, role in enumerate(ROLES)},
        **{
            key: value
            for key, value in vars(data).items()
            if key not in {"tolerance", "date_tolerance"}
        },
        title="SYNTHETIC nine-role interest procedure",
        rationale="Independent principal, interest, bank-rate and source-evidence controls",
    )
    result = workflow(params, "IN", sources)
    assert result["expected_total"] == "93.23" and not result["blocked"]
    assert result["interest_bank_controls"][0]["gross_principal_allocated"] == "900"
    assert result["interest_bank_controls"][0]["interest_allocated"] == "90"
    assert result["interest_bank_controls"][0]["unallocated_outflow"] == "10"
    assert not result["statutory_calculation_qualified"]
    with pytest.raises(ValueError, match="unavailable"):
        workflow(params, "AE", sources)
    with pytest.raises(ValidationError, match="nine"):
        WorkflowInput(
            **{**params.model_dump(), "source_ids": dict(list(params.source_ids.items())[:-1])}
        )
    with pytest.raises(ValidationError, match="four"):
        WorkflowInput(**{**params.model_dump(), "workflow": "india-msme-payment-timing"})


def test_repo_rate_cannot_be_declared_as_an_rbi_bank_rate_source():
    data, tables = fixture()
    tables["bank_rates"][0]["rate_kind"] = "RBI_REPO_RATE"
    with pytest.raises(ValidationError):
        calculate(data, tables)


def test_saved_nine_role_population_matches_authored_controls_and_original_bytes():
    import hashlib
    import json
    from pathlib import Path

    from app.modules.country_workflows.msme_interest_schemas import ROLES

    root = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-msme-interest"
    )
    manifest = json.loads((root / "controls.json").read_text(encoding="utf-8"))
    assert manifest["synthetic"] and not manifest["qualified_real_client"]
    tables = {}
    for role, table_type in ROLES.items():
        spec = manifest["files"][role]
        raw = (root / spec["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == spec["sha256"]
        # Preparation supplies actual retained document UUID/SHA. Pure parsing uses
        # explicitly synthetic placeholders, never claiming physical verification.
        import csv
        import io

        records = list(csv.DictReader(io.StringIO(raw.decode())))
        if role in {"interest_policies", "bank_rates"}:
            for row in records:
                row["source_evidence_version_id"] = "00000000-0000-4000-8000-000000000001"
                row["source_sha256"] = "a" * 64
        from tests.unit.test_country_workflows import parsed

        tables[role] = parsed(table_type, records)["rows"]
        assert len(tables[role]) == spec["expected_rows"]
    for name, spec in manifest["documents"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == spec["sha256"]
    data, _ = settled_fixture()
    result = calculate(data, tables)
    assert result["expected_total"] == manifest["expected_total"]
    assert result["principal_timing_exception_count"] == manifest["principal_timing_exceptions"]
    assert result["rows"][0]["state"] == "MATCHED"
    bank = result["interest_bank_controls"][0]
    assert {
        key: bank[key]
        for key in ("gross_principal_allocated", "interest_allocated", "unallocated_outflow")
    } == {key: value for key, value in manifest["bank_budget"].items() if key != "original_outflow"}
