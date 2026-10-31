"""Synthetic evidence controls, not professional or client qualification."""

import uuid
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.employment_payroll import ROLES, ROW_TYPES
from app.modules.country_workflows.schemas import WorkflowInput
from tests.unit.test_shared_audit_workflows import source


def population(currency="AED"):
    common = dict(
        registration="SYNTHETIC-EMPLOYER",
        employee_token="a" * 64,
        episode_reference="SYN-EP1",
        component="GROSS",
        currency=currency,
        evidence_reference="SYNTHETIC-EVIDENCE",
    )
    episode = dict(
        common,
        id="E1",
        started_on="2026-06-15",
        ended_on=None,
        assessment="Synthetic contract episode independently assessed",
    )
    observation = dict(
        common,
        payroll_month="2026-06",
        earning_month="2026-06",
        category="regular",
        entry_reference="SYN-ENTRY",
        amount="1000",
    )
    control = dict(
        observation,
        id="C1",
        service_from="2026-06-15",
        service_through="2026-06-30",
        contract_reference="SYN-CONTRACT",
        attendance_reference="SYN-ATTENDANCE",
        assessment="Synthetic independent expected pay; no formula inferred",
    )
    register = dict(
        observation, id="R1", revision=1, record_status="current", run_reference="SYN-RUN"
    )
    return dict(employment=[episode], controls=[control], register=[register])


def run(p=None, country="AE", **changes):
    p = p if p is not None else population()
    sources = {role: source(ROLES[role], rows) for role, rows in p.items()}
    params = WorkflowInput.model_validate(
        dict(
            workflow="employment-payroll-review",
            source_ids={role: uuid.uuid4() for role in sources},
            period_start=changes.pop("period_start", "2026-06-01"),
            as_of=changes.pop("as_of", "2026-06-30"),
            title="SYNTHETIC employment payroll",
            rationale="Independent expected payroll, episode and service evidence assessed",
            **changes,
        )
    )
    return calculate(params, country, sources)


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
def test_joiner_independent_expected_pay_not_automatic_proration(country, currency):
    p = population(currency)
    original = deepcopy(p)
    result = run(p, country)
    assert p == original and not result["blocked"] and result["exception_count"] == 0
    assert len(result["rows"]) == 2
    assert result["rows"][0]["expected_amount"] == "1000"


def test_missing_both_pay_and_control_is_not_zero():
    p = population()
    p["controls"] = []
    p["register"] = []
    result = run(p)
    assert result["blocked"]
    assert result["rows"][0]["state"] == "MISSING_EMPLOYEE_MONTH_CONTROL"
    assert result["rows"][0]["expected_amount"] is None


def test_every_declared_month_requires_control():
    result = run(as_of="2026-07-31")
    assert result["blocked"]
    assert any(
        r["state"] == "MISSING_EMPLOYEE_MONTH_CONTROL" and r["payroll_month"] == "2026-07"
        for r in result["rows"]
    )


def test_service_before_joining_blocks_equal_amounts():
    p = population()
    p["controls"][0]["service_from"] = "2026-06-01"
    assert run(p)["rows"][0]["state"] == "SERVICE_OUTSIDE_EMPLOYMENT"


def test_arrears_after_termination_use_original_earning_service():
    p = population()
    p["employment"][0]["ended_on"] = "2026-06-30"
    for role in ("controls", "register"):
        p[role][0].update(payroll_month="2026-07", category="arrears")
    result = run(p, period_start="2026-07-01", as_of="2026-07-31")
    assert not result["blocked"]


def test_correction_retains_every_revision_and_counts_latest_once():
    p = population()
    old = dict(p["register"][0], id="R0", amount="1500", record_status="superseded")
    p["register"][0]["revision"] = 2
    p["register"].append(old)
    result = run(p)
    assert not result["blocked"] and result["rows"][0]["reported_amount"] == "1000"
    history = [r for r in result["rows"] if r["kind"] == "revision-history"]
    assert len(history) == 2 and sum(r["counted_in_current_payroll"] for r in history) == 1
    assert {r["retained_amount"] for r in history} == {"1500", "1000"}
    assert all(r["episode_reference"] == "SYN-EP1" for r in history)


@pytest.mark.parametrize("mode", ["duplicate", "two-current", "stale-current", "all-superseded"])
def test_ambiguous_revisions_fail_closed(mode):
    p = population()
    second = dict(p["register"][0], id="R2", revision=2)
    if mode == "duplicate":
        second["revision"] = 1
    if mode == "stale-current":
        second["record_status"] = "cancelled"
    if mode == "all-superseded":
        p["register"][0]["record_status"] = second["record_status"] = "superseded"
    p["register"].append(second)
    with pytest.raises(ValueError, match="revisions"):
        run(p)


def test_cancelled_latest_does_not_establish_zero():
    p = population()
    p["register"][0]["record_status"] = "cancelled"
    assert run(p)["rows"][0]["state"] == "MISSING_CURRENT_PAYROLL"


@pytest.mark.parametrize(
    "field,value",
    [
        ("registration", "OTHER"),
        ("employee_token", "b" * 64),
        ("episode_reference", "OTHER"),
        ("currency", "USD"),
        ("component", "BONUS"),
    ],
)
def test_identity_partitions_do_not_offset(field, value):
    p = population()
    p["register"][0][field] = value
    result = run(p)
    assert result["blocked"] and any(
        r["state"] == "MISSING_CURRENT_PAYROLL" for r in result["rows"]
    )


def test_equal_total_cannot_hide_offsetting_entry_variances():
    p = population()
    for role in ("controls", "register"):
        p[role].append(dict(p[role][0], id=role + "2", entry_reference="SYN-SECOND"))
    p["register"][0]["amount"] = "1100"
    p["register"][1]["amount"] = "900"
    assert sum(r["state"] == "PAYROLL_AMOUNT_VARIANCE" for r in run(p)["rows"]) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("employee_token", "Employee Name"),
        ("revision", True),
        ("revision", 1.5),
        ("amount", 1.1),
        ("payroll_month", "2026-13"),
        ("payroll_month", "0000-01"),
        ("employee_name", "Private Name"),
    ],
)
def test_invalid_or_identifying_canonical_fields_rejected(field, value):
    row = dict(population()["register"][0], **{field: value})
    with pytest.raises((ValueError, ValidationError)):
        ROW_TYPES[ROLES["register"]].model_validate(row)


def test_closed_calendar_months_required():
    with pytest.raises(ValueError, match="calendar months"):
        run(period_start="2026-06-02")


def test_decimal_differences_preserve_low_units_on_large_salary():
    p = population()
    p["controls"][0]["amount"] = "99999999999999999999.00000001"
    p["register"][0]["amount"] = "99999999999999999999.00000002"
    result = run(p, tolerance="0")
    assert result["rows"][0]["difference"] == "1E-8" and result["blocked"]
