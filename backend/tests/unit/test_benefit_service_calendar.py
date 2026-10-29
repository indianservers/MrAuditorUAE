"""Authored dated service-day cases; no statutory or client qualification."""

import csv
import hashlib
import io
import json
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from openpyxl import load_workbook

from app.modules.country_workflows.benefit_service_calendar import SCOPE, TABLE, ServiceExclusion
from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
from app.modules.country_workflows.sources import parse_csv
from app.modules.intelligence.exports import render
from tests.unit.test_practice_audit_workflows import (
    benefit_employee,
    benefit_rule,
    part_time_employee,
)
from tests.unit.test_shared_audit_workflows import run as legacy_run
from tests.unit.test_shared_audit_workflows import source as original_source


def record(employee=None, **changes):
    employee = employee or benefit_employee()
    return {
        **{key: employee[key] for key in SCOPE},
        "id": "EX-" + employee["id"],
        "employee_id": employee["id"],
        "kind": "EXCLUDED_CALENDAR_DAYS",
        "exclusion_start": "2026-05-01",
        "exclusion_end": "2026-05-05",
        "days": 5,
        "evidence_reference": "SYNTHETIC-ASSESSED-HR-REGISTER",
        "assessment": "Synthetic independently assessed calendar-day exclusion, not pension service",
        **changes,
    }


def zero(employee=None, **changes):
    return record(
        employee,
        kind="NO_EXCLUDED_DAYS_ASSESSED",
        exclusion_start=None,
        exclusion_end=None,
        days=0,
        **changes,
    )


def calendar_source(rows, **changes):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(ServiceExclusion.model_fields))
    writer.writeheader()
    writer.writerows(rows)
    data = SourceInput(
        evidence_version_id=uuid4(),
        table_type=TABLE,
        label="Synthetic dated service register",
        expected_rows=len(rows),
        benefit_service_controls={
            "employee_count": len({r["employee_id"] for r in rows}),
            "excluded_days": sum(r["days"] for r in rows),
        },
        **changes,
    )
    return parse_csv(stream.getvalue().encode(), data)


def run(employees=None, records=None, *, country="AE", calendar=None, rules=None):
    employees = employees if employees is not None else [benefit_employee(excluded_service_days=5)]
    records = records if records is not None else [record(employees[0])]
    sources = {
        "employees": original_source("benefit-employees", employees),
        "rules": original_source(
            "benefit-rules", rules or [benefit_rule(minimum_service_years="0")]
        ),
        "service_calendar": calendar if calendar is not None else calendar_source(records),
    }
    data = WorkflowInput(
        workflow="uae-benefit-review",
        source_ids={role: uuid4() for role in sources},
        as_of="2026-06-30",
        currency="AED",
        title="Synthetic dated service check",
        rationale="Independently authored calendar and exclusion total controls",
    )
    return calculate(data, country, sources)


def test_adjacent_split_intervals_and_explicit_zero_preserve_full_and_part_time_benefits():
    full = benefit_employee(excluded_service_days=5, amount="2071.23")
    part = part_time_employee(id="E2")
    records = [
        record(full, id="SECOND", exclusion_start="2026-05-03", days=3),
        zero(part),
        record(full, id="FIRST", exclusion_end="2026-05-02", days=2),
    ]
    original = deepcopy(records)
    out = run(
        [full, part],
        records,
        rules=[
            benefit_rule(minimum_service_years="0"),
            benefit_rule(id="PART", work_model="part-time"),
        ],
    )
    assert records == original and not out["blocked"]
    assert out["service_calendar_basis"] == "DATED_CONTROLLED_SOURCE"
    assert out["benefit_service_controls"] == {"employee_count": 2, "excluded_days": 5}
    assert [r["expected_benefit"] for r in out["rows"]] == ["2071.23", "1050.00"]
    assert out["rows"][0]["eligible_service_days"] == 360
    assert [r["id"] for r in out["rows"][0]["service_calendar_records"]] == ["FIRST", "SECOND"]
    assert out["rows"][1]["calendar_excluded_service_days"] == 0


def test_exclusions_can_cross_the_supplied_minimum_service_boundary_without_inventing_a_rate():
    out = run([benefit_employee(excluded_service_days=5, amount="0")], rules=[benefit_rule()])
    assert not out["blocked"] and out["rows"][0]["expected_benefit"] == "0.00"
    assert out["rows"][0]["service_calendar_state"] == "MATCHED"


def test_missing_calendar_is_unknown_and_different_declared_days_block_expected_settlement():
    employees = [benefit_employee(excluded_service_days=6), part_time_employee(id="E2")]
    out = run(employees, [record(employees[0])])
    assert out["blocked"] and approval_error(out)
    assert out["rows"][0]["state"] == "EXCLUDED_SERVICE_DAYS_DIFFER"
    assert out["rows"][1]["state"] == "SERVICE_CALENDAR_MISSING"
    assert out["rows"][1]["calendar_excluded_service_days"] is None
    assert all("expected_benefit" not in r for r in out["rows"])


@pytest.mark.parametrize(
    "changes",
    [
        {"exclusion_start": "2025-06-30"},
        {"exclusion_end": "2026-07-01"},
        {"exclusion_start": "2026-05-06"},
        {"days": 4},
        {"days": 0},
        {"exclusion_start": None},
        {"assessment": " " * 20},
        {"kind": "NO_EXCLUDED_DAYS_ASSESSED"},
        {"scheme": "alternative"},
    ],
)
def test_outside_service_partial_or_unassessed_exclusions_are_rejected(changes):
    with pytest.raises(ValueError):
        calendar_source([record(**changes)])


@pytest.mark.parametrize("start", ["2026-05-01", "2026-05-05"])
def test_duplicate_or_overlapping_inclusive_periods_cannot_be_counted_twice(start):
    with pytest.raises(ValueError, match="Overlapping"):
        calendar_source(
            [record(), record(id="OTHER", exclusion_start=start, exclusion_end=start, days=1)]
        )


def test_leap_day_is_a_calendar_day_and_zero_record_cannot_mix_with_periods():
    employee = benefit_employee(service_start="2024-01-01")
    source = calendar_source(
        [record(employee, exclusion_start="2024-02-28", exclusion_end="2024-03-01", days=3)]
    )
    assert source["benefit_service_controls"]["excluded_days"] == 3
    with pytest.raises(ValueError, match="zero"):
        calendar_source([record(), zero(id="ZERO")])


@pytest.mark.parametrize(
    "field,value",
    [
        ("service_start", "2024-07-01"),
        ("regime", "OTHER"),
        ("cohort", "OTHER"),
        ("work_model", "part-time"),
    ],
)
def test_a_matching_day_total_cannot_replace_the_exact_employee_service_scope(field, value):
    with pytest.raises(ValueError, match="employment scopes"):
        run(records=[record(**{field: value})])


def test_unknown_employee_and_replayed_or_missing_controls_fail_closed():
    with pytest.raises(ValueError, match="unique employees"):
        run(records=[record(employee_id="UNKNOWN")])
    for field, value in [
        ("benefit_service_controls", None),
        ("benefit_service_controls", {"employee_count": 1, "excluded_days": 4}),
        ("benefit_service_calendar_contract", "old"),
    ]:
        source = calendar_source([record()])
        source[field] = value
        with pytest.raises(ValueError):
            run(calendar=source)


@pytest.mark.parametrize(
    "controls",
    [
        None,
        {"employee_count": 0, "excluded_days": 0},
        {"employee_count": True, "excluded_days": 0},
        {"employee_count": 1, "excluded_days": -1},
    ],
)
def test_source_requires_independent_integer_population_and_day_controls(controls):
    with pytest.raises(ValueError):
        SourceInput(
            evidence_version_id=uuid4(),
            table_type=TABLE,
            label="Synthetic source",
            expected_rows=1,
            benefit_service_controls=controls,
        )


def test_empty_calendar_cannot_mean_zero_and_india_does_not_reuse_uae_benefit_rules():
    with pytest.raises(ValueError):
        calendar_source([])
    with pytest.raises(ValueError, match="unavailable"):
        run(country="IN")


def test_large_calendar_export_preserves_each_dated_record_and_original_body():
    employee = benefit_employee(service_start="2024-01-01", excluded_service_days=400)
    start = date(2024, 1, 1)
    records = [
        record(
            employee,
            id=f"EX-{i}",
            exclusion_start=(start + timedelta(days=i)).isoformat(),
            exclusion_end=(start + timedelta(days=i)).isoformat(),
            days=1,
        )
        for i in range(400)
    ]
    body = run([employee], records)
    assert not body["blocked"]
    original = deepcopy(body)
    event = {
        "id": "SYN-CALENDAR",
        "kind": "country-workflow",
        "version": 1,
        "sha256": "a" * 64,
        "created_at": "2026-06-30T00:00:00Z",
        "dependencies": [],
        "body": body,
    }
    content, _ = render(event, "xlsx")
    rows = list(load_workbook(io.BytesIO(content))["Benefit service exclusions"].values)
    assert len(rows) == 401 and rows[-1][rows[0].index("id")] == "EX-399"
    assert rows[-1][rows[0].index("exclusion_end")] == (start + timedelta(days=399)).isoformat()
    assert body == original


def test_without_calendar_the_existing_amount_remains_an_explicit_employee_declaration():
    out = legacy_run(
        "uae-benefit-review", {"employees": [benefit_employee()], "rules": [benefit_rule()]}
    )
    assert out["rows"][0]["expected_benefit"] == "2100.00"
    assert out["service_calendar_basis"] == "EMPLOYEE_DECLARATION_ONLY"
    assert out["rows"][0]["calendar_excluded_service_days"] is None


def test_original_calendar_identifiers_are_not_silently_trimmed():
    with pytest.raises(ValueError, match="silently trimmed"):
        calendar_source([record(evidence_reference=" SYNTHETIC-REFERENCE ")])


def test_saved_example_bytes_controls_and_authored_expectations_agree():
    root = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-benefit-service-calendar"
    )
    manifest = json.loads((root / "controls.json").read_text(encoding="utf-8"))
    sources = {}
    for role, specification in manifest["files"].items():
        content = (root / specification["file"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == specification["sha256"]
        parameters = {
            key: value for key, value in specification.items() if key not in {"file", "sha256"}
        }
        sources["service_calendar" if role == "exclusions" else role] = parse_csv(
            content,
            SourceInput(
                evidence_version_id=uuid4(), label="Synthetic saved calendar example", **parameters
            ),
        )
    sources["rules"] = original_source(
        "benefit-rules", [benefit_rule(), benefit_rule(id="PART", work_model="part-time")]
    )
    payload = WorkflowInput(
        workflow="uae-benefit-review",
        source_ids={role: uuid4() for role in sources},
        as_of=manifest["as_of"],
        currency="AED",
        title="Synthetic saved service calendar",
        rationale="Check original files against separately authored numeric expectations",
    )
    output = calculate(payload, "AE", sources)
    assert not output["blocked"] and output["exception_count"] == 0
    for row, expected in zip(output["rows"], manifest["authored_expected"], strict=True):
        assert row["id"] == expected["employee"]
        assert row["eligible_service_days"] == expected["eligible_service_days"]
        assert row["calendar_excluded_service_days"] == expected["excluded_days"]
        assert row["expected_benefit"] == expected["expected_benefit"]
