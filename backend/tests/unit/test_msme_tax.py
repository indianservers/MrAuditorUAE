"""Authored tax-year examples, not professional client qualification."""

from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.msme_tax import calculate
from app.modules.country_workflows.msme_tax_schemas import METRICS, MSMETaxSettlement
from tests.unit.test_msme_payments import populations


def fixture():
    tables = populations()
    tables["bank"][0]["date"] = "2026-03-31"
    parties = dict(
        buyer_id="SYNTHETIC-BUYER",
        supplier_id="SYNTHETIC-SUPPLIER",
        invoice_id="INV",
        currency="INR",
    )
    evidence = dict(
        source_url="https://synthetic.example/tax-assessment",
        source_evidence_version_id="00000000-0000-4000-8000-000000000001",
        source_sha256="a" * 64,
        source_version="SYNTHETIC tax basis",
        evidence_reference="SYNTHETIC retained assessment",
        applicability_review="Independent synthetic applicability and tax treatment, not legal qualification",
    )
    tables.update(
        tax_bases=[
            dict(
                id="BASIS",
                **parties,
                **evidence,
                amount="100",
                liability_tax_year_start="2025-04-01",
                otherwise_allowable=True,
                history_from="2026-01-01",
                history_assessment="Assessed complete invoice and bank settlement history",
                opening_paid_basis="0",
                opening_disallowed_basis="0",
                opening_previously_allowed_unpaid="0",
                tax_reference="1961:43B(h)",
                effective_from="2025-04-01",
                effective_to="2026-03-31",
                basis_assessment="Assessed otherwise allowable principal, excluding separately assessed items",
            )
        ],
        tax_settlements=[
            dict(
                id="PORTION",
                **parties,
                mode="BANK_ALLOCATION_PORTION",
                amount="100",
                bucket="CURRENT_EXPENSE",
                principal_allocation_id="LINK",
                qualifies_as_payment=True,
                evidence_reference="SYNTHETIC original bank portion",
                rationale="Assessed tax basis portion of the original gross bank payment",
            )
        ],
        interest_pnl=[
            dict(
                id="PNL",
                **parties,
                **evidence,
                amount="12",
                tax_year_start="2025-04-01",
                section23_applies=True,
                pnl_assessment="Assessed current P&L charge, not closing accrued interest",
            )
        ],
        reported=[
            dict(
                id="REPORT-" + str(i),
                **parties,
                metric=metric,
                tax_year_start="2025-04-01",
                as_of="2026-03-31",
                amount=amount,
                evidence_reference="SYNTHETIC independently prepared tax computation",
            )
            for i, (metric, amount) in enumerate(zip(METRICS, ("12", "0", "0"), strict=True))
        ],
    )
    data = SimpleNamespace(
        msme_buyer_id="SYNTHETIC-BUYER",
        account="SYNTHETIC-ACCOUNT",
        currency="INR",
        as_of=date(2026, 3, 31),
        tax_year_start=date(2025, 4, 1),
        tax_observed_through=date(2026, 3, 31),
        obligation_month_start="2026-01",
        obligation_month_end="2026-01",
        settlement_start=date(2026, 1, 1),
        bank_payment_sign="debit-negative",
        tolerance=0,
        date_tolerance=0,
    )
    return data, tables


def amounts(result):
    return {row["metric"]: row["expected_amount"] for row in result["rows"]}


def test_current_paid_expense_and_pnl_charge_are_separate():
    data, tables = fixture()
    result = calculate(data, tables)
    assert amounts(result) == dict(zip(METRICS, ("12", "0", "0"), strict=True))
    assert result["net_expected_tax_adjustment"] == "12" and not result["blocked"]
    assert result["exception_count"] == 0 and result["form26_targets"] is None


def test_late_payment_in_same_year_has_no_current_addback_but_retains_timing_exception():
    data, tables = fixture()
    tables["bank"][0]["date"] = "2026-02-01"
    result = calculate(data, tables)
    assert amounts(result)[METRICS[1]] == "0" and result["principal_timing_exception_count"] == 1


def test_late_payment_after_year_end_is_not_rescued_by_filing_date():
    data, tables = fixture()
    data.tax_observed_through = date(2026, 5, 1)
    tables["bank"][0]["date"] = "2026-04-01"
    result = calculate(data, tables)
    assert amounts(result)[METRICS[1]] == "100"
    assert result["invoice_tax_details"][0]["closing_disallowed_carry"] == "100"


@pytest.mark.parametrize(
    "payment,observed,expected",
    [
        ("2026-04-04", "2026-04-04", "0"),
        ("2026-04-05", "2026-04-05", "100"),
        (None, "2026-04-04", None),
        (None, "2026-04-05", "100"),
    ],
)
def test_post_year_deadline_needs_actual_observation_not_zero_default(payment, observed, expected):
    data, tables = fixture()
    data.obligation_month_start = data.obligation_month_end = "2026-03"
    tables["invoices"][0].update(invoice_date="2026-03-20", delivery_date="2026-03-20")
    tables["tax_bases"][0]["history_from"] = "2026-03-20"
    data.tax_observed_through = date.fromisoformat(observed)
    tables["interest_pnl"][0]["amount"] = "0"
    tables["reported"][0]["amount"] = "0"
    if payment:
        tables["bank"][0]["date"] = payment
    else:
        tables["bank"] = []
        tables["allocations"] = []
        tables["tax_settlements"] = []
    result = calculate(data, tables)
    assert amounts(result)[METRICS[1]] == expected
    assert result["blocked"] == (expected is None)


def prior_fixture():
    data, tables = fixture()
    b = tables["tax_bases"][0]
    b.update(
        liability_tax_year_start="2024-04-01",
        opening_paid_basis="0",
        opening_disallowed_basis="60",
        opening_previously_allowed_unpaid="40",
        prior_disallowance_reference="1961:43B(h)",
    )
    tables["invoices"][0].update(invoice_date="2025-03-20", delivery_date="2025-03-20")
    tables["assessments"][0]["scope_start"] = "2025-01-01"
    data.obligation_month_start = data.obligation_month_end = "2025-03"
    data.settlement_start = date(2025, 3, 1)
    b["history_from"] = "2025-03-01"
    tables["bank"].append(
        {**tables["bank"][0], "id": "ALLOWED", "date": "2025-04-04", "amount": "-40"}
    )
    tables["allocations"].append(
        {**tables["allocations"][0], "id": "ALLOWED-LINK", "payment_id": "ALLOWED", "amount": "40"}
    )
    tables["tax_settlements"].append(
        {
            **tables["tax_settlements"][0],
            "id": "ALLOWED-PORTION",
            "principal_allocation_id": "ALLOWED-LINK",
            "amount": "40",
            "bucket": "PRIOR_ALREADY_ALLOWED",
        }
    )
    tables["bank"][0]["amount"] = "-60"
    tables["allocations"][0]["amount"] = "60"
    tables["tax_settlements"][0].update(amount="60", bucket="PRIOR_DISALLOWED")
    tables["reported"][2]["amount"] = "60"
    return data, tables


def test_prior_release_never_releases_previously_allowed_unpaid_amount():
    data, tables = prior_fixture()
    r = calculate(data, tables)
    assert amounts(r)[METRICS[2]] == "60" and r["net_expected_tax_adjustment"] == "-48"
    tables["tax_settlements"] = [tables["tax_settlements"][1]]
    tables["bank"] = [tables["bank"][1]]
    tables["allocations"] = [tables["allocations"][1]]
    r = calculate(data, tables)
    assert (
        amounts(r)[METRICS[2]] == "0"
        and r["invoice_tax_details"][0]["closing_disallowed_carry"] == "60"
    )


def test_future_observed_payment_does_not_release_prior_carry_in_this_year():
    data, tables = prior_fixture()
    data.tax_observed_through = date(2026, 4, 1)
    tables["bank"][0]["date"] = "2026-04-01"
    assert amounts(calculate(data, tables))[METRICS[2]] == "0"


@pytest.mark.parametrize(
    "fault",
    [
        "missing-portion",
        "missing-basis",
        "unknown-otherwise",
        "short-history",
        "short-policy",
        "missing-pnl",
        "unknown-pnl",
    ],
)
def test_unknown_facts_never_become_a_zero_adjustment(fault):
    data, tables = fixture()
    if fault == "missing-portion":
        tables["tax_settlements"] = []
    elif fault == "missing-basis":
        tables["tax_bases"] = []
    elif fault == "unknown-otherwise":
        tables["tax_bases"][0]["otherwise_allowable"] = None
    elif fault == "short-history":
        tables["tax_bases"][0]["history_from"] = "2026-01-02"
    elif fault == "short-policy":
        tables["tax_bases"][0]["effective_to"] = "2026-03-30"
    elif fault == "missing-pnl":
        tables["interest_pnl"] = []
    else:
        tables["interest_pnl"][0]["section23_applies"] = None
    r = calculate(data, tables)
    assert r["blocked"] and r["net_expected_tax_adjustment"] is None
    assert any(row["expected_amount"] is None for row in r["rows"])


def other_settlement(tables, qualifies=True):
    b = tables["tax_bases"][0]
    return dict(
        id="OTHER",
        **{
            key: b[key]
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
                "evidence_reference",
            )
        },
        mode="ASSESSED_OTHER_SETTLEMENT",
        amount="20",
        bucket="CURRENT_EXPENSE",
        day="2026-02-01",
        qualifies_as_payment=qualifies,
        settlement_kind="WITHHOLDING",
        rationale="Independent retained tax treatment for this separately evidenced settlement",
    )


@pytest.mark.parametrize("qualifies,expected", [(True, "0"), (False, "20"), (None, None)])
def test_noncash_tax_treatment_is_explicit_and_not_inferred_from_bank(qualifies, expected):
    data, tables = fixture()
    tables["bank"][0]["amount"] = "-80"
    tables["allocations"][0]["amount"] = "80"
    tables["tax_settlements"][0]["amount"] = "80"
    tables["tax_settlements"].append(other_settlement(tables, qualifies))
    assert amounts(calculate(data, tables))[METRICS[1]] == expected


def test_net_pnl_credit_is_retained_without_becoming_negative_form33_disallowance():
    data, tables = fixture()
    tables["interest_pnl"][0]["amount"] = "-12"
    tables["reported"][0]["amount"] = "-12"
    r = calculate(data, tables)
    assert amounts(r)[METRICS[0]] is None and r["blocked"]
    assert r["invoice_tax_details"][0]["interest_pnl_assessment"]["amount"] == "-12"
    assert r["rows"][0]["state"] == "INTEREST_NET_CREDIT_REQUIRES_SEPARATE_TAX_TREATMENT"


@pytest.mark.parametrize(
    "fault",
    [
        "wrong-law",
        "wrong-party",
        "duplicate-report",
        "bank-overportion",
        "duplicate-portion",
        "wrong-bucket",
        "wrong-opening",
        "duplicate-other",
    ],
)
def test_conflicting_tax_evidence_is_rejected(fault):
    data, tables = fixture()
    if fault == "wrong-law":
        tables["tax_bases"][0]["tax_reference"] = "2025:37(2)(g)"
    elif fault == "wrong-party":
        tables["tax_bases"][0]["supplier_id"] = "ANOTHER"
    elif fault == "duplicate-report":
        tables["reported"].append({**tables["reported"][0], "id": "DUP"})
    elif fault == "bank-overportion":
        tables["tax_settlements"][0]["amount"] = "101"
    elif fault == "duplicate-portion":
        tables["tax_settlements"].append({**tables["tax_settlements"][0], "id": "DUP"})
    elif fault == "wrong-bucket":
        tables["tax_settlements"][0]["bucket"] = "PRIOR_DISALLOWED"
    elif fault == "wrong-opening":
        tables["tax_bases"][0]["opening_disallowed_basis"] = "1"
    else:
        tables["tax_settlements"] = [
            other_settlement(tables),
            {**other_settlement(tables), "id": "DUP"},
        ]
        tables["allocations"] = []
    with pytest.raises(ValueError):
        calculate(data, tables)


def test_bank_portion_cannot_override_original_date_or_claim_noncash_evidence():
    _, tables = fixture()
    row = tables["tax_settlements"][0]
    for change in [
        dict(day="2026-01-15"),
        dict(source_evidence_version_id="00000000-0000-4000-8000-000000000001"),
        dict(qualifies_as_payment=False),
    ]:
        with pytest.raises(ValidationError):
            MSMETaxSettlement.model_validate({**row, **change})


def test_new_act_reference_uses_explicit_form26_targets_only_for_current_period():
    data, tables = fixture()
    data.tax_year_start = date(2026, 4, 1)
    data.as_of = data.tax_observed_through = date(2027, 3, 31)
    data.obligation_month_start = data.obligation_month_end = "2026-06"
    tables["invoices"][0].update(invoice_date="2026-06-01", delivery_date="2026-06-01")
    tables["bank"][0]["date"] = "2026-06-17"
    tables["tax_bases"][0].update(
        liability_tax_year_start="2026-04-01",
        tax_reference="2025:37(2)(g)",
        effective_from="2026-04-01",
        effective_to="2027-03-31",
    )
    tables["interest_pnl"][0]["tax_year_start"] = "2026-04-01"
    for row in tables["reported"]:
        row.update(tax_year_start="2026-04-01", as_of="2027-03-31")
    r = calculate(data, tables)
    assert list(r["form26_targets"].values()) == ["33(a)", "33(b)", "33(c)"]


def annual_population(other=False):
    data, tables = fixture()
    data.tax_year_start = date(2026, 4, 1)
    data.as_of, data.tax_observed_through = date(2027, 3, 31), date(2027, 4, 5)
    data.settlement_start = date(2026, 3, 1)
    data.obligation_month_start, data.obligation_month_end = "2026-03", "2027-03"
    tables["assessments"][0]["scope_end"] = "2027-12-31"
    tables["invoices"][0].update(
        invoice_date="2027-03-20", delivery_date="2027-03-20", reference="SYN-CURRENT"
    )
    tables["bank"][0].update(date="2027-04-05", amount="-80" if other else "-100")
    tables["allocations"][0]["amount"] = "80" if other else "100"
    tables["tax_settlements"][0]["amount"] = "80" if other else "100"
    tables["tax_bases"][0].update(
        liability_tax_year_start="2026-04-01",
        tax_reference="2025:37(2)(g)",
        effective_from="2026-04-01",
        effective_to="2027-03-31",
        history_from="2027-03-20",
    )
    tables["interest_pnl"][0].update(tax_year_start="2026-04-01", amount="0")
    tables["reported"][0]["amount"] = "0"
    for row in tables["reported"]:
        row.update(tax_year_start="2026-04-01", as_of="2027-03-31")
    tables["reported"][1]["amount"] = "80" if other else "100"
    prior = {
        **deepcopy(tables["invoices"][0]),
        "id": "PRIOR",
        "reference": "SYN-PRIOR",
        "invoice_date": "2026-03-20",
        "delivery_date": "2026-03-20",
        "amount": "200",
    }
    tables["invoices"].append(prior)
    tables["bank"].append(
        {
            **tables["bank"][0],
            "id": "BANK-PRIOR",
            "reference": "SYN-PRIOR-BANK",
            "date": "2027-01-16",
            "amount": "-150",
        }
    )
    tables["allocations"].append(
        {
            **tables["allocations"][0],
            "id": "LINK-PRIOR",
            "item_id": "PRIOR",
            "payment_id": "BANK-PRIOR",
            "amount": "150",
        }
    )
    tables["tax_bases"].append(
        {
            **tables["tax_bases"][0],
            "id": "BASIS-PRIOR",
            "invoice_id": "PRIOR",
            "amount": "200",
            "liability_tax_year_start": "2025-04-01",
            "history_from": "2026-03-01",
            "opening_disallowed_basis": "150",
            "opening_previously_allowed_unpaid": "50",
            "prior_disallowance_reference": "1961:43B(h)",
        }
    )
    tables["tax_settlements"].append(
        {
            **tables["tax_settlements"][0],
            "id": "PORTION-PRIOR",
            "invoice_id": "PRIOR",
            "amount": "150",
            "bucket": "PRIOR_DISALLOWED",
            "principal_allocation_id": "LINK-PRIOR",
        }
    )
    tables["interest_pnl"].append(
        {**tables["interest_pnl"][0], "id": "PNL-PRIOR", "invoice_id": "PRIOR", "amount": "15"}
    )
    for i, (metric, amount) in enumerate(zip(METRICS, ("15", "0", "150"), strict=True)):
        tables["reported"].append(
            {
                **tables["reported"][i],
                "id": "PRIOR-REPORT-" + str(i),
                "invoice_id": "PRIOR",
                "metric": metric,
                "amount": amount,
            }
        )
    tables["bank"].append(
        {**tables["bank"][0], "id": "PRIOR-ALLOWED", "date": "2026-04-04", "amount": "-50"}
    )
    tables["allocations"].append(
        {
            **tables["allocations"][0],
            "id": "PRIOR-ALLOWED-LINK",
            "item_id": "PRIOR",
            "payment_id": "PRIOR-ALLOWED",
            "amount": "50",
        }
    )
    tables["tax_settlements"].append(
        {
            **tables["tax_settlements"][0],
            "id": "PRIOR-ALLOWED-PORTION",
            "invoice_id": "PRIOR",
            "principal_allocation_id": "PRIOR-ALLOWED-LINK",
            "amount": "50",
            "bucket": "PRIOR_ALREADY_ALLOWED",
        }
    )
    if other:
        tables["tax_settlements"].append({**other_settlement(tables), "day": "2027-03-31"})
    return data, tables


@pytest.mark.parametrize("other,expected", [(False, "-35"), (True, "-55")])
def test_eight_role_population_and_net_adjustment_do_not_sum_all_metrics_as_addbacks(
    other, expected
):
    import uuid

    from app.modules.country_workflows.calculations import calculate as workflow
    from app.modules.country_workflows.msme_tax_schemas import ROLES
    from app.modules.country_workflows.schemas import ROW_TYPES, WorkflowInput
    from tests.unit.test_country_workflows import parsed

    data, tables = annual_population(other)
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
        workflow="india-msme-annual-tax",
        source_ids={role: uuid.uuid4() for role in ROLES},
        title="SYNTHETIC assessed annual tax",
        rationale="Independent tax bases, opening balances and actual settlement observations",
        **vars(data),
    )
    result = workflow(params, "IN", sources)
    assert result["net_expected_tax_adjustment"] == expected and result["exception_count"] == 0
    assert not result["statutory_calculation_qualified"] and len(result["rows"]) == 6
    with pytest.raises(ValueError, match="unavailable"):
        workflow(params, "AE", sources)


def test_bank_portions_cannot_hide_payments_when_no_excluded_invoice_basis_exists():
    data, tables = fixture()
    tables["tax_settlements"][0]["amount"] = "80"
    with pytest.raises(ValueError, match="outside its assessed tax basis"):
        calculate(data, tables)


def test_assessed_advance_application_keeps_original_cash_date_and_separate_tax_date():
    data, tables = fixture()
    tables["interest_pnl"][0]["amount"] = "0"
    tables["reported"][0]["amount"] = "0"
    data.settlement_start = date(2025, 3, 1)
    tables["tax_bases"][0]["history_from"] = "2025-03-01"
    tables["bank"][0]["date"] = "2025-03-16"
    assert calculate(data, tables)["blocked"]
    tables["tax_settlements"][0] = {
        **other_settlement(tables),
        "id": "APPLIED",
        "mode": "ASSESSED_BANK_ADVANCE_APPLICATION",
        "amount": "100",
        "settlement_kind": "ADVANCE_APPROPRIATION",
        "principal_allocation_id": "LINK",
        "day": "2026-01-01",
    }
    result = calculate(data, tables)
    assert amounts(result)[METRICS[1]] == "0" and not result["blocked"]
    event = result["invoice_tax_details"][0]["tax_settlements"][0]
    assert event["payment_day"] == "2026-01-01"
    assert event["original_bank_allocation"]["payment_date"] == "2025-03-16"
    tables["tax_settlements"][0]["day"] = "2025-03-15"
    with pytest.raises(ValueError, match="precede its original bank"):
        calculate(data, tables)


@pytest.mark.parametrize("fault", ["late", "missing"])
def test_prior_already_allowed_balance_needs_timely_settlement_evidence(fault):
    data, tables = prior_fixture()
    if fault == "late":
        tables["bank"][1]["date"] = "2025-04-05"
    else:
        tables["bank"] = tables["bank"][:1]
        tables["allocations"] = tables["allocations"][:1]
        tables["tax_settlements"] = tables["tax_settlements"][:1]
    result = calculate(data, tables)
    assert result["blocked"]
    assert amounts(result)[METRICS[2]] is None
    assert (
        result["invoice_tax_details"][0]["principal_tax_issue"]
        == "PRIOR_ALLOWANCE_WITHOUT_TIMELY_SETTLEMENT_REQUIRES_TAX_REVIEW"
    )


@pytest.mark.parametrize("fault", ["paid-timely", "future-deadline"])
def test_positive_interest_cannot_override_contradictory_principal_timing(fault):
    data, tables = fixture()
    if fault == "paid-timely":
        tables["bank"][0]["date"] = "2026-01-16"
    else:
        data.obligation_month_start = data.obligation_month_end = "2026-03"
        tables["invoices"][0].update(invoice_date="2026-03-20", delivery_date="2026-03-20")
        tables["tax_bases"][0]["history_from"] = "2026-03-20"
    result = calculate(data, tables)
    assert result["blocked"] and amounts(result)[METRICS[0]] is None
    assert (
        result["invoice_tax_details"][0]["interest_pnl_issue"]
        == "PNL_INTEREST_SCOPE_CONTRADICTS_PRINCIPAL_TIMING"
    )


def test_saved_eight_role_population_has_original_byte_controls_and_separate_metrics():
    import csv
    import hashlib
    import io
    import json
    from pathlib import Path

    from app.modules.country_workflows.msme_tax_schemas import ROLES
    from tests.unit.test_country_workflows import parsed

    root = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-msme-tax"
    )
    manifest = json.loads((root / "controls.json").read_text(encoding="utf-8"))
    assert manifest["synthetic"] and not manifest["qualified_real_client"]
    tables = {}
    for role, table_type in ROLES.items():
        spec = manifest["files"][role]
        raw = (root / spec["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == spec["sha256"]
        records = list(csv.DictReader(io.StringIO(raw.decode())))
        if role in {"tax_bases", "interest_pnl"}:
            for row in records:
                row["source_evidence_version_id"] = "00000000-0000-4000-8000-000000000001"
                row["source_sha256"] = "a" * 64
        tables[role] = parsed(table_type, records)["rows"]
        assert len(tables[role]) == spec["expected_rows"] > 0
    for name, spec in manifest["documents"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == spec["sha256"]
    data, _ = annual_population()
    result = calculate(data, tables)
    assert result["net_expected_tax_adjustment"] == manifest["net_expected_tax_adjustment"] == "-35"
    assert result["tax_totals"] == manifest["tax_totals"]
    assert not result["blocked"] and result["exception_count"] == 0
    assert len(result["invoice_tax_details"][1]["tax_settlements"]) == 2
