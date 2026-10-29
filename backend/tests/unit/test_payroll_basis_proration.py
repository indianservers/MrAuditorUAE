"""Authored wage-segment mechanics; these fixtures do not qualify client/legal cohorts."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.payroll_basis_proration import (
    COMPONENTS,
    CONTRACT,
    PayrollBasisSegment,
    PayrollCapRule,
    calculate,
    prorate,
)
from app.modules.country_workflows.payroll_calculations import payroll_rules
from app.modules.country_workflows.payroll_proration_source import ProratedBasisInput, source_rows
from app.modules.country_workflows.review import approval_error


def fixture():
    tables = {"segments": [], "rules": [], "controls": []}
    for cohort in "ABC":
        for component in sorted(COMPONENTS):
            basis = {
                "id": f"{cohort}:{component}",
                "registration": "SYN-EST",
                "subject": f"SYN-{cohort}",
                "period": "2026-09",
                "component": component,
                "currency": "INR",
                "rule_group": cohort,
                "jurisdiction": "SYNTHETIC",
                "eligible": True,
                "eligibility_reference": "SYN-MEMBERSHIP",
                "assessment": "Synthetic assessed membership option only",
            }
            newly_covered = cohort == "A" or (cohort == "B" and component == "PF:EPS")
            amount = "9333.33" if newly_covered else "20000.00" if cohort == "B" else "17333.33"
            tables["controls"].append({**basis, "amount": amount})
            for part, start, end, days in [("before", 1, 16, 16), ("after", 17, 30, 14)]:
                tables["segments"].append(
                    {
                        **basis,
                        "id": basis["id"] + ":" + part,
                        "amount": str(prorate("20000", days, 30)),
                        "segment_start": f"2026-09-{start:02}",
                        "segment_end": f"2026-09-{end:02}",
                        "monthly_reference_basis": "20000",
                        "proration_method": "ACTUAL_CALENDAR_MONTH_PAISE",
                        "eligible": not (newly_covered and part == "before"),
                    }
                )
                actual = cohort == "B" and component != "PF:EPS"
                tables["rules"].append(
                    {
                        "id": basis["id"] + ":policy:" + part,
                        "rule_group": cohort,
                        "component": component,
                        "jurisdiction": "SYNTHETIC",
                        "effective_from": f"2026-09-{start:02}",
                        "effective_to": f"2026-09-{end:02}",
                        "cap_mode": "ASSESSED_ACTUAL_BASIS" if actual else "CAPPED",
                        "monthly_ceiling": None
                        if actual
                        else "15000"
                        if part == "before"
                        else "25000",
                        "source_url": "https://synthetic.invalid/assessed-policy",
                        "source_sha256": "a" * 64,
                        "source_evidence_version_id": str(UUID(int=1)),
                        "source_version": "SYNTHETIC-1",
                        "evidence_reference": "SYN-POLICY",
                        "applicability_review": "Synthetic reviewed cohort ceiling option",
                    }
                )
    data = SimpleNamespace(
        currency="INR", tolerance=Decimal(0), date_tolerance=0, as_of=date(2026, 9, 30)
    )
    return data, tables


def result():
    data, tables = fixture()
    return {"workflow": "india-payroll-basis-proration", **calculate(data, tables)}


def request(**changes):
    return ProratedBasisInput(
        result_id=UUID(int=9),
        expected_rows=9,
        control_total="129333.31",
        label="Synthetic dated wage source",
        assessment="Independent synthetic monthly control schedule",
        **changes,
    )


def test_three_distinct_assessed_cohorts_and_existing_monthly_contribution_flow():
    body = result()
    assert not body["blocked"] and body["monthly_basis_complete"]
    assert body["payroll_proration_contract"] == CONTRACT
    rows, totals = source_rows(body, request())
    assert totals == {"INR": "129333.31"}
    assert len(rows) == 9 and all(len(r["proration_segments"]) == 2 for r in rows)
    rules, reported = [], []
    amounts = {
        "SYN-A": ("1120.00", "777.47", "342.53"),
        "SYN-B": ("2400.00", "777.47", "1622.53"),
        "SYN-C": ("2080.00", "1443.87", "636.13"),
    }
    for row in rows:
        eps = row["component"] == "PF:EPS"
        rules.append(
            {
                "id": "rate:" + row["id"],
                "rule_group": row["rule_group"],
                "component": row["component"],
                "jurisdiction": row["jurisdiction"],
                "effective_from": "2026-09-01",
                "effective_to": "2026-09-30",
                "threshold_from": "0",
                "threshold_to": None,
                "salary_cap": None,
                "formula": "employer-minus-eps" if row["component"] == "PF:EMPLOYER" else "rate",
                "rate": "0.0833" if eps else "0.12",
                "fixed_amount": None,
                "rounding": "paise",
                "source_version": "SYN-RATE",
                "source_sha256": "b" * 64,
                "source_url": "https://synthetic.invalid/rate",
            }
        )
        index = {"PF:EMPLOYEE": 0, "PF:EPS": 1, "PF:EMPLOYER": 2}[row["component"]]
        reported.append({**row, "amount": amounts[row["subject"]][index]})
    data, _ = fixture()
    monthly = payroll_rules(data, {"bases": rows, "rules": rules, "reported": reported})
    assert not monthly["blocked"] and monthly["expected_total_complete"]
    assert all(r["state"] == "MATCHED" for r in monthly["rows"])
    assert all(len(r["segment_source_ids"]) == 2 for r in monthly["rows"])
    rules[0]["salary_cap"] = "15000"
    blocked = payroll_rules(data, {"bases": rows, "rules": rules, "reported": reported})
    assert blocked["blocked"] and not blocked["expected_total_complete"]
    assert any(
        r["state"] == "POST_CAP_BASIS_REQUIRES_UNCAPPED_RATE_WITHOUT_WAGE_SLABS"
        for r in blocked["rows"]
    )


@pytest.mark.parametrize(
    "change",
    [
        {"segment_start": "2026-08-31"},
        {"segment_end": "2026-09-01"},
        {"amount": "10666.66"},
        {"monthly_reference_basis": "-1"},
        {"proration_method": "ASSUMED_THIRTY_DAY"},
        {"component": "PT"},
        {"currency": "AED"},
        {"assessment": "          "},
    ],
)
def test_invalid_segments(change):
    _, tables = fixture()
    with pytest.raises((ValidationError, ValueError)):
        PayrollBasisSegment.model_validate({**tables["segments"][0], **change})


@pytest.mark.parametrize(
    "change",
    [
        {"cap_mode": "CAPPED", "monthly_ceiling": None},
        {"cap_mode": "ASSESSED_ACTUAL_BASIS", "monthly_ceiling": "15000"},
        {"monthly_ceiling": "0"},
        {"effective_to": "2026-08-31"},
        {"applicability_review": "          "},
    ],
)
def test_policy_missing_ceiling_never_means_uncapped(change):
    _, tables = fixture()
    with pytest.raises(ValidationError):
        PayrollCapRule.model_validate({**tables["rules"][0], **change})


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("gap", "SEGMENT_GAP_OR_OVERLAP"),
        ("overlap", "SEGMENT_GAP_OR_OVERLAP"),
        ("policy_missing", "CEILING_POLICY_MISSING_SPLIT_OR_AMBIGUOUS"),
        ("policy_ambiguous", "CEILING_POLICY_MISSING_SPLIT_OR_AMBIGUOUS"),
        ("policy_inside", "CEILING_POLICY_MISSING_SPLIT_OR_AMBIGUOUS"),
        ("amount", "MONTH_BASIS_CONTROL_DIFFERENCE"),
        ("eligibility", "MONTH_ELIGIBILITY_CONTROL_DIFFERENCE"),
        ("jurisdiction", "MONTH_CONTROL_SCOPE_DIFFERENCE"),
    ],
)
def test_incomplete_populations_block_without_fabricating_zero(mutation, expected):
    data, tables = fixture()
    if mutation == "gap":
        tables["segments"][0]["segment_start"] = "2026-09-02"
        tables["segments"][0]["amount"] = "10000.00"
    elif mutation == "overlap":
        tables["segments"][1]["segment_start"] = "2026-09-16"
        tables["segments"][1]["amount"] = "10000.00"
    elif mutation == "policy_missing":
        tables["rules"].pop(0)
    elif mutation in {"policy_ambiguous", "policy_inside"}:
        policy = {**tables["rules"][0], "id": "extra-policy"}
        if mutation == "policy_inside":
            policy["effective_from"] = "2026-09-05"
        tables["rules"].append(policy)
    elif mutation == "amount":
        tables["controls"][0]["amount"] = "0"
    elif mutation == "eligibility":
        tables["controls"][0]["eligible"] = False
    elif mutation == "jurisdiction":
        tables["controls"][0]["jurisdiction"] = "OTHER"
    body = calculate(data, tables)
    assert body["blocked"] and not body["monthly_basis_complete"]
    assert expected in {r["state"] for r in body["rows"]}
    for row in body["rows"]:
        if row["state"] not in {"MATCHED", "MONTH_BASIS_CONTROL_DIFFERENCE"}:
            assert row["computed_monthly_basis"] is None


def test_missing_component_is_not_an_excluded_zero():
    data, tables = fixture()
    tables["controls"] = [r for r in tables["controls"] if r["component"] != "PF:EPS"]
    tables["segments"] = [r for r in tables["segments"] if r["component"] != "PF:EPS"]
    with pytest.raises(ValueError, match="all three"):
        calculate(data, tables)


@pytest.mark.parametrize(
    "field,value",
    [
        ("currency", "AED"),
        ("tolerance", Decimal("0.01")),
        ("date_tolerance", 1),
        ("as_of", date(2026, 9, 29)),
    ],
)
def test_scope_guards(field, value):
    data, tables = fixture()
    setattr(data, field, value)
    with pytest.raises(ValueError):
        calculate(data, tables)


def test_parent_contract_and_control_checks_preserve_original():
    body = result()
    original = deepcopy(body)
    assert approval_error(body) is None
    for field, value in [
        ("blocked", True),
        ("monthly_basis_complete", False),
        ("payroll_proration_contract", "old"),
    ]:
        with pytest.raises(ValueError):
            source_rows({**body, field: value}, request())
    for field, value in [("expected_rows", 8), ("control_total", "0")]:
        data = request().model_copy(update={field: value})
        with pytest.raises(ValueError):
            source_rows(body, data)
    assert body == original
    assert approval_error({**body, "payroll_proration_contract": "old"})


def test_leap_month_and_precision_are_explicit():
    assert prorate("10000000000000000000.12345678", 1, 29) == Decimal("344827586206896551.73")
    _, tables = fixture()
    row = {
        **tables["segments"][0],
        "period": "2024-02",
        "segment_start": "2024-02-01",
        "segment_end": "2024-02-29",
        "amount": "20000.00",
    }
    assert PayrollBasisSegment.model_validate(row).segment_end.day == 29


def test_explicit_excluded_month_has_a_resolved_zero_not_missing_membership():
    data, tables = fixture()
    for row in tables["segments"]:
        row["eligible"] = False
    for control in tables["controls"]:
        control.update(eligible=False, amount="0")
    body = calculate(data, tables)
    assert not body["blocked"]
    assert all(r["computed_monthly_basis"] == "0" for r in body["rows"])


def test_missing_month_control_is_not_a_resolved_zero():
    data, tables = fixture()
    tables["controls"].pop(0)
    body = calculate(data, tables)
    missing = next(r for r in body["rows"] if r["state"] != "MATCHED")
    assert body["blocked"] and missing["computed_monthly_basis"] is None


def test_large_export_keeps_each_segment_outside_excel_cell_limits():
    import io

    from openpyxl import load_workbook

    from app.modules.intelligence.exports import render

    body = result()
    original_segment = deepcopy(body["rows"][0]["segment_trace"][0])
    body["rows"][0]["segment_trace"] = [
        {**original_segment, "id": f"synthetic-export-{index}", "assessment": "X" * 2000}
        for index in range(400)
    ]
    original = deepcopy(body)
    content, _ = render(
        {
            "id": "SYN-PRORATION",
            "kind": "country-workflow",
            "version": 1,
            "sha256": "a" * 64,
            "created_at": "2026-09-30T00:00:00Z",
            "dependencies": [],
            "body": body,
        },
        "xlsx",
    )
    workbook = load_workbook(io.BytesIO(content))
    records = list(workbook["Payroll basis segments"].values)
    assert len(records) == 417
    assert records[400][records[0].index("id")] == "synthetic-export-399"
    assert records[400][records[0].index("assessment")] == "X" * 2000
    summary = list(workbook["Rows"].values)
    assert "complete detail" in summary[1][summary[0].index("segment_trace")]
    assert body == original


def test_canonical_source_controls_and_country_guards():
    import csv
    import io

    from app.modules.country_workflows.calculations import calculate as workflow
    from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
    from app.modules.country_workflows.sources import parse_csv

    data, tables = fixture()
    sources = {}
    for role, table_type in [
        ("segments", "payroll-basis-segments"),
        ("rules", "payroll-cap-rules"),
        ("controls", "payroll-bases"),
    ]:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(tables[role][0]))
        writer.writeheader()
        writer.writerows(tables[role])
        totals = (
            {"INR": str(sum((Decimal(r["amount"]) for r in tables[role]), Decimal(0)))}
            if role != "rules"
            else {}
        )
        parameters = SourceInput(
            evidence_version_id=UUID(int=len(sources) + 100),
            table_type=table_type,
            label="Synthetic independently controlled PF source",
            expected_rows=len(tables[role]),
            control_totals=totals,
        )
        sources[role] = parse_csv(buffer.getvalue().encode(), parameters)
    parameters = WorkflowInput(
        workflow="india-payroll-basis-proration",
        source_ids={r: UUID(int=i + 1) for i, r in enumerate(sources)},
        as_of=data.as_of,
        currency="INR",
        title="Synthetic calendar wage controls",
        rationale="Original segments compared with independent monthly wage bases",
    )
    assert not workflow(parameters, "IN", sources)["blocked"]
    with pytest.raises(ValueError, match="unavailable"):
        workflow(parameters, "AE", sources)
    with pytest.raises(ValidationError):
        parameters.model_validate({**parameters.model_dump(), "tolerance": "0.01"})


def test_saved_synthetic_source_bytes_controls_and_authored_expectations():
    import hashlib
    import json
    from pathlib import Path

    from app.modules.country_workflows.schemas import SourceInput
    from app.modules.country_workflows.sources import parse_csv

    root = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-payroll-proration"
    )
    manifest = json.loads((root / "controls.json").read_text())
    tables = {}
    for role, spec in manifest["files"].items():
        content = (root / spec["file"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == spec["sha256"]
        parameters = {key: value for key, value in spec.items() if key not in {"file", "sha256"}}
        source = parse_csv(
            content,
            SourceInput(
                evidence_version_id=UUID(int=10), label="Synthetic saved wage basis", **parameters
            ),
            defaults={"source_evidence_version_id": str(UUID(int=1)), "source_sha256": "a" * 64}
            if role == "rules"
            else None,
        )
        tables[role] = source["rows"]
    data, _ = fixture()
    body = calculate(data, tables)
    assert not body["blocked"]
    assert [
        {key: row[key] for key in expected}
        for row, expected in zip(body["rows"], manifest["authored_expected"], strict=True)
    ] == manifest["authored_expected"]
