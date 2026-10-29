"""Authored savings mechanics; rates and membership are supplied assumptions."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.contribution_source import ContributionSourceInput, source_rows
from app.modules.country_workflows.obligation_scope import scope_key
from app.modules.country_workflows.savings_reported_source import (
    SavingsReportedInput,
)
from app.modules.country_workflows.savings_reported_source import (
    source_rows as reported_rows,
)
from app.modules.country_workflows.savings_scheme import (
    COMPONENT,
    CONTRACT,
    SavingsBasis,
    SavingsObservation,
    SavingsRule,
    calculate,
)
from app.modules.country_workflows.schemas import Obligation


def fixture():
    base = {
        "id": "SYN-E1",
        "registration": "SYN-EMPLOYER",
        "subject": "SYN-E1",
        "period": "2026-06",
        "authority": "MOHRE",
        "scheme": "MOHRE_SAVINGS",
        "fund_id": "SYN-FUND-1",
        "membership_reference": "SYN-MEMBER-1",
        "enrolled_on": "2026-01-01",
        "coverage_start": "2026-06-01",
        "coverage_end": "2026-06-30",
        "regime": "SYN-REGIME",
        "cohort": "SYN-COHORT",
        "work_model": "full-time",
        "component": COMPONENT,
        "currency": "AED",
        "amount": "10000",
        "evidence_reference": "SYN-BASIC-WAGE",
        "employment_start": "2024-01-01",
        "employment_end": None,
        "eligible": True,
        "rate_band": "SYN-LOW",
        "rate_band_assessment": "Synthetic independently assessed service-rate band",
        "salary_basis_kind": "CONTRACT_BASIC",
        "annual_contract_hours": None,
        "annual_full_time_hours": None,
        "basis_method": "FULL_MONTH_BASIC",
        "period_basis_assessment": "Synthetic full-month contributory basic wage only",
        "enrolment_evidence_version_id": str(UUID(int=1)),
        "enrolment_sha256": "a" * 64,
    }
    second = {
        **base,
        "id": "SYN-E2",
        "subject": "SYN-E2",
        "fund_id": "SYN-FUND-2",
        "membership_reference": "SYN-MEMBER-2",
        "employment_start": "2010-01-01",
        "amount": "3000",
        "rate_band": "SYN-HIGH",
    }
    part = {
        **base,
        "id": "SYN-E3",
        "subject": "SYN-E3",
        "membership_reference": "SYN-MEMBER-3",
        "work_model": "part-time",
        "salary_basis_kind": "ASSESSED_FULL_TIME_COMPARATOR",
        "annual_contract_hours": "1040",
        "annual_full_time_hours": "2080",
    }
    partial = {
        **base,
        "id": "SYN-E4",
        "subject": "SYN-E4",
        "membership_reference": "SYN-MEMBER-4",
        "enrolled_on": "2026-06-16",
        "coverage_start": "2026-06-16",
        "basis_method": "ASSESSED_COVERED_PERIOD_BASIC",
        "amount": "5000",
    }
    bases = [base, second, part, partial]
    policy = {
        "id": "SYN-R1",
        "authority": "MOHRE",
        "scheme": "MOHRE_SAVINGS",
        "fund_id": "SYN-FUND-1",
        "regime": "SYN-REGIME",
        "cohort": "SYN-COHORT",
        "work_model": "full-time",
        "rate_band": "SYN-LOW",
        "rate": "0.0583",
        "rounding": "nearest-fils",
        "effective_from": "2026-01-01",
        "effective_to": "2026-12-31",
        "source_url": "https://synthetic.invalid/savings-policy",
        "source_sha256": "b" * 64,
        "source_evidence_version_id": str(UUID(int=2)),
        "source_version": "SYNTHETIC-1",
        "evidence_reference": "SYN-RULE",
        "applicability_review": "Synthetic assessed rate, regime and comparator applicability",
    }
    rules = [
        policy,
        {
            **policy,
            "id": "SYN-R2",
            "fund_id": "SYN-FUND-2",
            "rate_band": "SYN-HIGH",
            "rate": "0.0833",
        },
        {**policy, "id": "SYN-R3", "work_model": "part-time"},
    ]
    reported = []
    for row, value in zip(bases, ["583.00", "249.90", "291.50", "291.50"], strict=True):
        observed = {
            key: value for key, value in row.items() if key in SavingsObservation.model_fields
        }
        reported.append(
            {
                **observed,
                "id": "FUND-" + row["id"],
                "amount": value,
                "evidence_reference": "SYN-FUND-STATEMENT",
            }
        )
    data = SimpleNamespace(
        currency="AED", tolerance=Decimal(0), date_tolerance=0, as_of=date(2026, 6, 30)
    )
    return data, {"bases": bases, "rules": rules, "reported": reported}


def body():
    data, tables = fixture()
    return {
        "workflow": "uae-savings-review",
        "savings_document_binding": "RETAINED_DOCUMENT_BYTES_VERIFIED",
        **calculate(data, tables),
    }


def request():
    return ContributionSourceInput(
        result_id=UUID(int=100),
        due_date_evidence_version_id=UUID(int=3),
        label="Synthetic savings expectations",
        assessment="Independent fund-specific count, amount and due date controls",
        groups=[
            dict(
                registration="SYN-EMPLOYER",
                period="2026-06",
                component=COMPONENT,
                fund_id=fund,
                expected_rows=count,
                amount=amount,
                due_date="2026-07-15",
                due_date_reference="SYN-DATE",
            )
            for fund, count, amount in [("SYN-FUND-1", 3, "1166.00"), ("SYN-FUND-2", 1, "249.90")]
        ],
    )


def test_full_part_time_and_explicit_covered_period_to_expected_remittances():
    result = body()
    assert result["savings_contribution_contract"] == CONTRACT
    assert not result["blocked"] and result["expected_total_complete"]
    assert result["expected_total"] == "1415.90"
    assert all(row["state"] == "MATCHED" for row in result["rows"])
    part = next(r for r in result["rows"] if r["subject"] == "SYN-E3")
    assert part["hours_ratio"] == "0.5" and part["expected_amount"] == "291.50"
    original = deepcopy(result)
    rows, totals, excluded = source_rows(result, request())
    assert len(rows) == 4 and totals == {"AED": "1415.90"} and not excluded
    assert all(r["savings_scope"]["fund_id"] in {"SYN-FUND-1", "SYN-FUND-2"} for r in rows)
    assert all(r["payment_date"] is None for r in rows)
    assert result == original


@pytest.mark.parametrize(
    "change",
    [
        {"enrolled_on": "2026-07-01"},
        {"coverage_end": "2026-07-01"},
        {"period": "2026-07"},
        {"employment_start": "2026-02-01"},
        {"employment_end": "2026-06-15"},
        {"annual_contract_hours": "1040"},
        {"salary_basis_kind": "ASSESSED_FULL_TIME_COMPARATOR"},
        {"rate_band_assessment": "          "},
        {"period_basis_assessment": "          "},
        {"currency": "INR"},
        {"component": "PENSION:EMPLOYER"},
        {"scheme": "DIFC_DEWS"},
        {"amount": "-1"},
    ],
)
def test_invalid_basis_does_not_silently_change_scheme_or_salary(change):
    _, tables = fixture()
    with pytest.raises(ValidationError):
        SavingsBasis.model_validate({**tables["bases"][0], **change})


@pytest.mark.parametrize(
    "change",
    [
        {"salary_basis_kind": "CONTRACT_BASIC"},
        {"annual_contract_hours": None},
        {"annual_full_time_hours": None},
        {"annual_contract_hours": "3000"},
        {"annual_contract_hours": "0"},
    ],
)
def test_part_time_cannot_prorate_an_actual_contract_salary_again(change):
    _, tables = fixture()
    with pytest.raises(ValidationError):
        SavingsBasis.model_validate({**tables["bases"][2], **change})


@pytest.mark.parametrize(
    "method,expected",
    [("nearest-fils", "194.33"), ("next-fils", "194.34"), ("floor-fils", "194.33")],
)
def test_ratio_precision_and_round_once(method, expected):
    data, tables = fixture()
    tables["bases"][2].update(annual_contract_hours="1", annual_full_time_hours="3")
    tables["rules"][2]["rounding"] = method
    out = calculate(data, tables)
    row = next(r for r in out["rows"] if r["subject"] == "SYN-E3")
    assert row["expected_amount"] == expected


@pytest.mark.parametrize("kind", ["missing", "overlap", "inside-change"])
def test_missing_or_competing_policy_blocks_unknown_instead_of_zero(kind):
    data, tables = fixture()
    if kind == "missing":
        tables["rules"].pop(0)
    else:
        rule = {**tables["rules"][0], "id": "OTHER"}
        if kind == "inside-change":
            rule["effective_from"] = "2026-06-15"
        tables["rules"].append(rule)
    out = calculate(data, tables)
    assert out["blocked"] and not out["expected_total_complete"]
    assert any(
        r["state"] == "RULE_MISSING_SPLIT_OR_AMBIGUOUS" and r["expected_amount"] is None
        for r in out["rows"]
    )


def test_zero_exclusion_is_resolved_but_missing_observation_is_not_zero():
    data, tables = fixture()
    tables["bases"][0]["eligible"] = False
    tables["reported"][0]["amount"] = "0"
    out = calculate(data, tables)
    assert out["rows"][0]["expected_amount"] == "0.00" and out["rows"][0]["state"] == "MATCHED"
    tables["reported"].pop(0)
    out = calculate(data, tables)
    assert (
        out["rows"][0]["reported_amount"] is None
        and out["rows"][0]["state"] == "FUND_OBSERVATION_MISSING"
    )


def test_same_employee_overlapping_fund_or_work_model_rows_are_not_pooled():
    data, tables = fixture()
    tables["bases"].append({**tables["bases"][0], "id": "OTHER", "fund_id": "OTHER-FUND"})
    with pytest.raises(ValueError, match="Overlapping"):
        calculate(data, tables)


def test_fund_and_membership_identity_are_not_amount_only_matching_keys():
    data, tables = fixture()
    tables["reported"][0]["fund_id"] = "WRONG-FUND"
    out = calculate(data, tables)
    assert out["blocked"] and out["exception_count"] == 2
    assert {r["state"] for r in out["rows"]} >= {"BASIS_MISSING", "FUND_OBSERVATION_MISSING"}


def test_fund_control_cannot_be_omitted_or_pooled_across_funds():
    for groups in [
        [{**g.model_dump(), "fund_id": None} for g in request().groups],
        [{**request().groups[0].model_dump(), "expected_rows": 4, "amount": "1415.90"}],
    ]:
        data = request().model_copy(
            update={"groups": [type(request().groups[0]).model_validate(g) for g in groups]}
        )
        with pytest.raises(ValueError):
            source_rows(body(), data)


def test_fund_reported_derivation_keeps_original_scope_and_never_becomes_payment():
    _, tables = fixture()
    source = {"table_type": "savings-reported", "rows": tables["reported"]}
    data = SavingsReportedInput(
        source_id=UUID(int=8),
        expected_rows=4,
        control_total="1415.90",
        label="Synthetic fund statement observations",
        assessment="Independent original fund statement population and exact amount controls",
    )
    original = deepcopy(source)
    rows, totals = reported_rows(source, data)
    assert totals == {"AED": "1415.90"} and len(rows) == 4
    assert all(row["payment_date"] is None and row["due_date"] is None for row in rows)
    assert rows[0]["savings_scope"]["membership_reference"] == "SYN-MEMBER-1"
    assert scope_key(rows[0]) != scope_key(
        {**rows[0], "savings_scope": {**rows[0]["savings_scope"], "fund_id": "OTHER"}}
    )
    assert source == original
    with pytest.raises(ValueError):
        reported_rows(source, data.model_copy(update={"control_total": Decimal(0)}))


def test_nil_fund_observations_require_an_original_nil_assessment():
    data = SavingsReportedInput(
        source_id=UUID(int=8),
        expected_rows=0,
        control_total="0",
        label="Synthetic nil fund population",
        assessment="Original independently assessed nil observation population",
    )
    source = {"table_type": "savings-reported", "rows": []}
    with pytest.raises(ValueError, match="nil"):
        reported_rows(source, data)
    assert reported_rows(
        {**source, "nil_reason": "Synthetic independently reviewed absence of fund observations"},
        data,
    ) == ([], {"AED": "0"})


@pytest.mark.parametrize(
    "change",
    [
        {"component": "PENSION:EMPLOYER"},
        {"currency": "INR"},
        {"period": "2026-07"},
        {"population": "arrears"},
    ],
)
def test_bank_obligations_cannot_hide_savings_as_pension_or_other_month(change):
    rows, _, _ = source_rows(body(), request())
    canonical = {key: value for key, value in rows[0].items() if key in Obligation.model_fields}
    with pytest.raises(ValidationError):
        Obligation.model_validate({**canonical, **change})


def test_rule_dates_rates_and_assessments_are_explicit():
    _, tables = fixture()
    for change in [
        {"rate": "1.01"},
        {"effective_to": "2025-01-01"},
        {"applicability_review": "          "},
    ]:
        with pytest.raises(ValidationError):
            SavingsRule.model_validate({**tables["rules"][0], **change})


def test_scope_survives_bank_allocation_and_rejects_equal_amount_wrong_fund():
    from app.modules.country_workflows.dues_allocations import allocate
    from app.modules.country_workflows.schemas import WorkflowInput
    from tests.unit.country_workflow_cases import transaction

    expected, _, _ = source_rows(body(), request())
    _, population = fixture()
    control = SavingsReportedInput(
        source_id=UUID(int=8),
        expected_rows=4,
        control_total="1415.90",
        label="Synthetic original fund observations",
        assessment="Independent participant and fund amount controls",
    )
    reported, _ = reported_rows(
        {"table_type": "savings-reported", "rows": population["reported"]}, control
    )
    indexed = {r["subject"]: r["id"] for r in expected}
    links = [
        dict(
            id="A" + str(i),
            expected_id=indexed[r["subject"]],
            reported_id=r["id"],
            transaction_id="B1",
            currency="AED",
            amount=r["amount"],
            evidence_reference="SYN-ADVICE",
            rationale="Synthetic participant and fund payment allocation",
        )
        for i, r in enumerate(reported)
    ]
    data = WorkflowInput(
        workflow="obligation-bank-allocations",
        source_ids={
            r: UUID(int=i + 10)
            for i, r in enumerate(["expected", "reported", "bank", "allocations"])
        },
        as_of="2026-07-31",
        currency="AED",
        account="BANK-1",
        obligation_month_start="2026-06",
        obligation_month_end="2026-06",
        settlement_start="2026-07-01",
        bank_payment_sign="debit-negative",
        title="Synthetic savings bank controls",
        rationale="Independent expected, fund-reported and bank sources",
    )
    tables = {
        "expected": expected,
        "reported": reported,
        "bank": [transaction(id="B1", amount="-1415.90", date="2026-07-15")],
        "allocations": links,
    }
    out = allocate(data, tables, "AE")
    assert all(r["state"] == "MATCHED" for r in out["rows"])
    assert (
        out["rows"][0]["fund_id"] == "SYN-FUND-1"
        and out["rows"][0]["membership_reference"] == "SYN-MEMBER-1"
    )
    tables["reported"][0]["savings_scope"]["fund_id"] = "WRONG-FUND"
    with pytest.raises(ValueError):
        allocate(data, tables, "AE")
    with pytest.raises(ValueError):
        allocate(data, tables, "IN")


def test_source_csv_controls_country_and_purpose_guards():
    import csv
    import io

    from app.modules.country_workflows.calculations import calculate as workflow
    from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
    from app.modules.country_workflows.sources import parse_csv

    data, tables = fixture()
    sources = {}
    for role, table_type in [
        ("bases", "savings-bases"),
        ("rules", "savings-rules"),
        ("reported", "savings-reported"),
    ]:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(tables[role][0]))
        writer.writeheader()
        writer.writerows(tables[role])
        totals = (
            {"AED": "28000"}
            if role == "bases"
            else {"AED": "1415.90"}
            if role == "reported"
            else {}
        )
        parameters = SourceInput(
            evidence_version_id=UUID(int=len(sources) + 10),
            table_type=table_type,
            label="Synthetic original savings population",
            expected_rows=len(tables[role]),
            control_totals=totals,
        )
        sources[role] = parse_csv(buffer.getvalue().encode(), parameters)
    params = WorkflowInput(
        workflow="uae-savings-review",
        source_ids={r: UUID(int=i + 1) for i, r in enumerate(sources)},
        as_of=data.as_of,
        currency="AED",
        title="Synthetic original fund review",
        rationale="Independent original wages, assessed policies and fund observations",
    )
    assert not workflow(params, "AE", sources)["blocked"]
    with pytest.raises(ValueError, match="unavailable"):
        workflow(params, "IN", sources)
    with pytest.raises(ValidationError):
        WorkflowInput(**{**params.model_dump(), "tolerance": "0.01"})


def test_saved_original_bytes_and_authored_savings_controls():
    import hashlib
    import json
    from pathlib import Path

    from app.modules.country_workflows.schemas import SourceInput
    from app.modules.country_workflows.sources import parse_csv

    root = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-savings-scheme"
    )
    manifest = json.loads((root / "controls.json").read_text(encoding="utf-8"))
    for name, spec in manifest["documents"].items():
        content = (root / name).read_bytes()
        assert (
            hashlib.sha256(content).hexdigest() == spec["sha256"]
            and len(content) == spec["size_bytes"]
        )
    tables = {}
    for role, spec in manifest["files"].items():
        content = (root / spec["file"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == spec["sha256"]
        defaults = (
            {
                "enrolment_evidence_version_id": str(UUID(int=1)),
                "enrolment_sha256": manifest["documents"]["enrolment.txt"]["sha256"],
            }
            if role == "bases"
            else {
                "source_evidence_version_id": str(UUID(int=2)),
                "source_sha256": manifest["documents"]["policy.txt"]["sha256"],
            }
            if role == "rules"
            else None
        )
        parameters = {key: value for key, value in spec.items() if key not in {"file", "sha256"}}
        tables[role] = parse_csv(
            content,
            SourceInput(
                evidence_version_id=UUID(int=10),
                label="Saved synthetic savings source",
                **parameters,
            ),
            defaults,
        )["rows"]
    data, _ = fixture()
    out = calculate(data, tables)
    assert not out["blocked"] and out["expected_total"] == manifest["expected_total"]
    assert [
        {"subject": row["subject"], "expected_amount": row["expected_amount"]}
        for row in out["rows"]
    ] == manifest["authored_expected"]
