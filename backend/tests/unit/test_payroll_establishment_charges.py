from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.payroll_establishment_charges import (
    ChargeControl,
    ChargeRule,
    calculate,
)


def fixture():
    members = [
        {
            "id": f"m{i}",
            "registration": "SYNTHETIC-EST",
            "subject": str(i),
            "period": "2026-06",
            "component": "PF:ADMINISTRATION",
            "currency": "INR",
            "amount": "10000",
            "contributing": True,
            "evidence_reference": "SYNTHETIC assessed wages",
        }
        for i in (1, 2)
    ]
    control = {
        "id": "control",
        "registration": "SYNTHETIC-EST",
        "period": "2026-06",
        "component": "PF:ADMINISTRATION",
        "currency": "INR",
        "rule_group": "synthetic",
        "jurisdiction": "IN-SYNTHETIC",
        "expected_members": 2,
        "expected_contributors": 2,
        "amount": "20000",
        "establishment_state": "OTHER",
        "evidence_reference": "SYNTHETIC independent HR total",
        "assessment": "Synthetic reviewed establishment wage population and status",
    }
    rule = {
        "id": "rule",
        "component": "PF:ADMINISTRATION",
        "rule_group": "synthetic",
        "jurisdiction": "IN-SYNTHETIC",
        "rate": "0.005",
        "rounding": "nearest-rupee",
        "effective_from": "2026-01-01",
        "effective_to": "2026-12-31",
        "source_url": "https://synthetic.example/assessed-charge",
        "source_sha256": "a" * 64,
        "source_evidence_version_id": "00000000-0000-4000-8000-000000000001",
        "source_version": "Synthetic policy, not statutory qualification",
        "evidence_reference": "Synthetic reviewed rates",
        "applicability_review": "Synthetic explicitly reviewed rate and minimum fixtures",
        "aggregation": "SUM_BASES_THEN_ROUND",
        "minimum_other": "500",
        "minimum_non_functional": "75",
    }
    observation = {
        "id": "reported",
        "registration": "SYNTHETIC-EST",
        "subject": "SYNTHETIC-EST",
        "period": "2026-06",
        "component": "PF:ADMINISTRATION",
        "currency": "INR",
        "amount": "500",
    }
    return SimpleNamespace(
        currency="INR", tolerance=0, date_tolerance=0, as_of=date(2026, 6, 30)
    ), {
        "members": members,
        "controls": [control],
        "rules": [rule],
        "reported": [observation],
    }


def test_minimum_applies_once_to_establishment_not_per_member():
    data, tables = fixture()
    result = calculate(data, tables)
    assert not result["blocked"] and result["exception_count"] == 0
    row = result["rows"][0]
    assert row["charge_before_minimum"] == "100"
    assert row["expected_amount"] == "500"
    assert row["member_source_ids"] == ["m1", "m2"]


def test_reviewed_nil_member_population_still_has_establishment_minimum():
    data, tables = fixture()
    tables["members"] = []
    tables["controls"][0].update(
        expected_members=0,
        expected_contributors=0,
        amount="0",
        establishment_state="NON_FUNCTIONAL_NO_CONTRIBUTORS",
    )
    tables["reported"][0]["amount"] = "75"
    result = calculate(data, tables)
    assert result["rows"][0]["expected_amount"] == "75" and result["exception_count"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"expected_members": 3},
        {"expected_contributors": 1},
        {"amount": "19999"},
    ],
)
def test_mismatched_independent_controls_block_without_fabricating_zero(change):
    data, tables = fixture()
    tables["controls"][0].update(change)
    result = calculate(data, tables)
    assert result["blocked"] and not result["expected_total_complete"]
    assert result["rows"][0]["expected_amount"] is None


@pytest.mark.parametrize(
    "change", [{"effective_to": "2026-06-15"}, {"effective_from": "2026-06-16"}]
)
def test_partial_month_rules_block_even_with_other_full_month_candidate(change):
    data, tables = fixture()
    tables["rules"].append({**tables["rules"][0], "id": "competing", **change})
    assert calculate(data, tables)["rows"][0]["state"] == "RULE_MISSING_SPLIT_OR_AMBIGUOUS"


def test_establishments_cannot_pool_wages_or_minima():
    data, tables = fixture()
    for role in ("members", "controls", "reported"):
        copies = deepcopy(tables[role])
        for row in copies:
            row.update(id="second:" + row["id"], registration="SYNTHETIC-SECOND")
            if role == "reported":
                row["subject"] = "SYNTHETIC-SECOND"
        tables[role].extend(copies)
    result = calculate(data, tables)
    assert result["expected_total"] == "1000" and len(result["rows"]) == 2


def test_member_cap_and_rounding_are_separate_from_aggregate_rounding():
    data, tables = fixture()
    tables["rules"][0].update(
        aggregation="ROUND_MEMBERS_THEN_SUM", salary_cap="9999", minimum_other="0", rate="0.00505"
    )
    tables["reported"][0]["amount"] = "100"
    result = calculate(data, tables)
    assert result["rows"][0]["expected_amount"] == "100"
    tables["rules"][0].update(aggregation="SUM_BASES_THEN_ROUND", salary_cap=None)
    assert calculate(data, tables)["rows"][0]["expected_amount"] == "101"


def test_aggregate_payroll_cap_is_rejected():
    _, tables = fixture()
    with pytest.raises(ValidationError, match="combined payroll"):
        ChargeRule.model_validate({**tables["rules"][0], "salary_cap": "15000"})


def test_conflicting_administration_and_inspection_cannot_both_charge_same_month():
    data, tables = fixture()
    tables["controls"].append(
        {**tables["controls"][0], "id": "inspection", "component": "PF:INSPECTION"}
    )
    with pytest.raises(ValueError, match="mutually exclusive"):
        calculate(data, tables)


def test_duplicate_members_and_uncontrolled_populations_rejected():
    data, tables = fixture()
    tables["members"].append({**tables["members"][0], "id": "duplicate"})
    with pytest.raises(ValueError, match="Duplicate member"):
        calculate(data, tables)
    tables["members"][-1]["registration"] = "UNCONTROLLED"
    with pytest.raises(ValueError, match="explicit establishment control"):
        calculate(data, tables)


def test_unknown_reported_establishment_is_blocked_not_dropped():
    data, tables = fixture()
    tables["reported"].append(
        {**tables["reported"][0], "id": "extra", "registration": "UNKNOWN", "subject": "UNKNOWN"}
    )
    result = calculate(data, tables)
    assert result["blocked"] and len(result["rows"]) == 2
    assert result["rows"][1]["state"] == "CONTROL_MISSING"


def test_missing_reported_amount_is_absent_not_zero():
    data, tables = fixture()
    tables["reported"] = []
    row = calculate(data, tables)["rows"][0]
    assert (
        row["expected_amount"] == "500"
        and row["reported_amount"] is None
        and row["difference"] is None
    )


def test_non_contributors_cannot_conceal_positive_assessed_charge_wages():
    data, tables = fixture()
    tables["members"][0]["contributing"] = False
    with pytest.raises(ValidationError, match="zero assessed charge wage"):
        calculate(data, tables)


def test_functional_zero_population_does_not_infer_non_functional_minimum():
    data, tables = fixture()
    tables["members"] = []
    tables["controls"][0].update(expected_members=0, expected_contributors=0, amount="0")
    assert calculate(data, tables)["rows"][0]["expected_amount"] == "500"


def test_no_contributor_state_does_not_accept_positive_contributor_count():
    _, tables = fixture()
    with pytest.raises(ValidationError, match="zero contributors"):
        ChargeControl.model_validate(
            {**tables["controls"][0], "establishment_state": "NON_FUNCTIONAL_NO_CONTRIBUTORS"}
        )


def test_future_month_and_employee_observation_are_rejected():
    data, tables = fixture()
    data.as_of = date(2026, 6, 29)
    with pytest.raises(ValueError, match="month must be closed"):
        calculate(data, tables)
    data.as_of = date(2026, 6, 30)
    tables["reported"][0]["subject"] = "EMPLOYEE"
    with pytest.raises(ValueError, match="establishment-level"):
        calculate(data, tables)


def test_saved_original_populations_authored_totals_and_country_guards():
    import hashlib
    import json
    from pathlib import Path
    from uuid import UUID

    from app.modules.country_workflows.calculations import calculate as workflow
    from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
    from app.modules.country_workflows.sources import parse_csv

    root = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-establishment-charges"
    )
    manifest = json.loads((root / "controls.json").read_text(encoding="utf-8"))
    policy = (root / "policy.txt").read_bytes()
    assert hashlib.sha256(policy).hexdigest() == manifest["documents"]["policy.txt"]["sha256"]
    sources = {}
    for role, spec in manifest["files"].items():
        content = (root / spec["file"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == spec["sha256"]
        parameters = {key: value for key, value in spec.items() if key not in {"file", "sha256"}}
        sources[role] = parse_csv(
            content,
            SourceInput(
                evidence_version_id=UUID(int=1),
                label="Saved original synthetic charge population",
                **parameters,
            ),
            {
                "source_evidence_version_id": str(UUID(int=2)),
                "source_sha256": hashlib.sha256(policy).hexdigest(),
            }
            if role == "rules"
            else None,
        )
    params = WorkflowInput(
        workflow="india-establishment-charges",
        source_ids={role: UUID(int=i + 1) for i, role in enumerate(sources)},
        as_of="2026-06-30",
        currency="INR",
        title="Saved synthetic charge controls",
        rationale="Independent authored per-establishment totals, synthetic only",
    )
    result = workflow(params, "IN", sources)
    assert not result["blocked"] and result["exception_count"] == 0
    assert result["expected_total"] == manifest["expected_total"]
    assert [
        {key: row[key] for key in ("registration", "component", "expected_amount")}
        for row in result["rows"]
    ] == manifest["authored_expected"]
    with pytest.raises(ValueError, match="unavailable"):
        workflow(params, "AE", sources)
    with pytest.raises(ValidationError):
        WorkflowInput(**{**params.model_dump(), "tolerance": "1"})


@pytest.mark.parametrize("count", [True, "1.0", " 1", "+1", "01", -1])
def test_independent_member_counts_reject_coercion(count):
    _, tables = fixture()
    with pytest.raises(ValidationError):
        ChargeControl.model_validate({**tables["controls"][0], "expected_members": count})
