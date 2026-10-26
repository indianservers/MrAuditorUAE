"""Synthetic date/scope evidence; no ERP or country adoption is inferred."""

import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.grc import schemas as s
from app.modules.grc import sod_intervals as engine
from app.modules.grc.sod_import import parse


def assignment(permission, scope="A", start="2026-01-01", end=None, principal="user"):
    return dict(
        principal=principal, permission=permission, scope=scope, valid_from=start, valid_to=end
    )


def policy(**changes):
    body = dict(
        system="SYNTHETIC ERP",
        version_number=1,
        pairs=[dict(first="create", second="approve", rationale="Separate authorization")],
        definition_evidence_id=str(uuid.uuid4()),
        effective_from="2026-01-01",
    )
    body.update(changes)
    return s.SoDRule.model_validate(body)


def population(rows=None, historical=True, **changes):
    rows = rows or [assignment("create"), assignment("approve", end="2026-06-30")]
    body = dict(
        system="SYNTHETIC ERP",
        rule_id=str(uuid.uuid4()),
        as_of="2026-12-31",
        assignments=rows,
        source_evidence_id=str(uuid.uuid4()),
    )
    if historical:
        body.update(
            period_start="2026-01-01",
            population_basis="validity-history",
            coverage_start="2026-01-01",
            coverage_end="2026-12-31",
            history_scope_assessment="Synthetic full grant/revoke history assessed separately",
            expected_assignment_count=len(rows),
            expected_principal_count=len({r["principal"] for r in rows}),
            population_control_evidence_id=str(uuid.uuid4()),
            population_control_reference="Independent synthetic counts memo",
            source_hash="a" * 64,
        )
    body.update(changes)
    return s.SoDAccess.model_validate(body)


def test_revocation_before_year_end_is_only_detected_with_period_history():
    point = engine.calculate(policy(), population(historical=False))
    period = engine.calculate(policy(), population())
    assert point["count"] == 0
    assert period["count"] == 1
    assert period["conflict_intervals"][0]["conflict_through"] == "2026-06-30"
    assert period["assignment_pair_links"][0]["second_assignment_index"] == 2
    assert period["source_binding_status"] == "NOT_VERIFIED_BY_PURE_CALCULATOR"
    assert period["conflicts"][0]["compensating_control_verified"] is False


@pytest.mark.parametrize("start,count", [("2026-07-01", 0), ("2026-06-30", 1)])
def test_inclusive_date_boundary_without_ghost_overlap(start, count):
    result = engine.calculate(
        policy(),
        population([assignment("create", end="2026-06-30"), assignment("approve", start=start)]),
    )
    assert result["count"] == count
    if count:
        assert result["conflict_intervals"][0]["conflict_from"] == "2026-06-30"
        assert result["conflict_intervals"][0]["conflict_through"] == "2026-06-30"


def test_regrants_merge_days_and_retain_every_original_pair():
    rows = [
        assignment("approve"),
        assignment("create", end="2026-03-31"),
        assignment("create", start="2026-04-01", end="2026-06-30"),
        assignment("create", start="2026-08-01"),
        assignment("create", start="2027-01-01"),
    ]
    result = engine.calculate(policy(), population(rows))
    assert result["count"] == 1
    assert len(result["conflict_intervals"]) == 2
    assert len(result["assignment_pair_links"]) == 3
    assert result["conflict_intervals"][0]["conflict_through"] == "2026-06-30"
    assert result["assignments_intersecting_window"] == 4


def mapping(first="A", second="B"):
    return dict(
        first_scope=first,
        second_scope=second,
        rationale="Direct synthetic scope overlap reviewed",
        evidence_reference="Policy appendix 2",
    )


def test_only_direct_reviewed_scope_relationships_apply():
    rows = [
        assignment("create", "A"),
        assignment("approve", "B"),
        assignment("approve", "C"),
        assignment("approve", "*"),
    ]
    assert engine.calculate(policy(), population(rows))["count"] == 0
    result = engine.calculate(
        policy(scope_mode="reviewed-overlap", scope_overlaps=[mapping(), mapping("B", "C")]),
        population(rows),
    )
    assert result["count"] == 1
    conflict = result["conflicts"][0]
    assert conflict["scope"] is None
    assert conflict["scope_basis"] == "REVIEWED_DIRECT_OVERLAP"
    assert conflict["scope_evidence_reference"] == "Policy appendix 2"
    reverse = engine.calculate(
        policy(scope_mode="reviewed-overlap", scope_overlaps=[mapping()]),
        population([assignment("create", "B"), assignment("approve", "A")]),
    )
    assert reverse["count"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        dict(period_start="2027-01-01"),
        dict(population_basis="point-in-time-export"),
        dict(source_hash=""),
        dict(expected_assignment_count=3),
        dict(expected_assignment_count="2"),
        dict(expected_principal_count=True),
        dict(population_control_evidence_id=None),
        dict(population_control_reference=" "),
        dict(coverage_start="2026-01-02"),
        dict(coverage_end="2026-12-30"),
        dict(history_scope_assessment=""),
        dict(source_hash="not-a-hash"),
    ],
)
def test_history_requires_explicit_complete_metadata(changes):
    with pytest.raises(ValidationError):
        population(**changes)


def test_population_controls_are_separate_and_duplicate_rows_rejected():
    identifier = str(uuid.uuid4())
    with pytest.raises(ValidationError, match="separate"):
        population(source_evidence_id=identifier, population_control_evidence_id=identifier)
    with pytest.raises(ValidationError, match="Duplicate"):
        population([assignment("create"), assignment("create")])
    with pytest.raises(ValidationError, match="History coverage"):
        population(historical=False, coverage_start="2026-01-01")


@pytest.mark.parametrize(
    "changes",
    [
        dict(scope_mode="reviewed-overlap"),
        dict(scope_overlaps=[mapping()]),
        dict(scope_mode="reviewed-overlap", scope_overlaps=[mapping(), mapping("B", "A")]),
        dict(pairs=[dict(first="create", second="create", rationale="Self permission")]),
        dict(
            pairs=[
                dict(first="a", second="b", rationale="Separate"),
                dict(first="b", second="a", rationale="Reversed"),
            ]
        ),
        dict(effective_to="2025-12-31"),
    ],
)
def test_invalid_definition_rejected(changes):
    with pytest.raises(ValidationError):
        policy(**changes)


def test_policy_changes_must_be_partitioned():
    with pytest.raises(ValueError, match="entire analysis window"):
        engine.calculate(policy(effective_to="2026-06-30"), population())
    legacy = policy().model_copy(update={"effective_from": None})
    with pytest.raises(ValueError, match="effective-dated"):
        engine.calculate(legacy, population())
    assert (
        engine.calculate(legacy, population(historical=False))["definition_effective_from"] is None
    )


@pytest.mark.parametrize(
    "content",
    [
        b"principal,permission,scope,valid_from,scope\nu,create,A,2026-01-01,A\n",
        b"principal,permission,scope,valid_from\nu,create,A,2026-01-01T00:00:00Z\n",
        b"principal,permission,scope,valid_from\nu,create,A,20260101\n",
        b"principal,permission,scope,valid_from\nu,create, ,2026-01-01\n",
        b'principal,permission,scope,valid_from\n"u\nother",create,A,2026-01-01\n',
    ],
)
def test_ambiguous_csv_identifiers_dates_and_headers_rejected(content):
    with pytest.raises(ValueError):
        parse(content)


def test_ten_thousand_assignment_population_retains_all_conflicts():
    rows = [
        assignment(permission, principal=f"user-{i:04d}")
        for i in range(5000)
        for permission in ("create", "approve")
    ]
    result = engine.calculate(policy(), population(rows))
    assert result["source_assignments"] == 10000
    assert result["source_principals"] == 5000
    assert result["count"] == len(result["assignment_pair_links"]) == 5000
    assert result["conflicts"][-1]["principal"] == "user-4999"


@pytest.mark.parametrize("bound", ["MAX_SOURCE_PAIRS", "MAX_COMPARISONS"])
def test_bounds_fail_instead_of_truncating(monkeypatch, bound):
    monkeypatch.setattr(engine, bound, 1)
    with pytest.raises(ValueError, match="bound exceeded"):
        engine.calculate(
            policy(),
            population(
                [
                    assignment("create"),
                    assignment("approve"),
                    assignment("approve", start="2026-02-01"),
                ]
            ),
        )


def test_date_max_interval_union_has_no_overflow():
    assert engine.merged_intervals([(date.max, date.max), (date.max, date.max)]) == [
        (date.max, date.max)
    ]


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_saved_country_examples_match_exact_bytes_and_declared_expectations(country):
    import hashlib
    import json
    from pathlib import Path

    folder = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-sod-history"
        / country
    )
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["sha256"].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest
    rows = parse((folder / "SYNTHETIC-access.csv").read_bytes())
    for history in (False, True):
        for reviewed in (False, True):
            rule = policy(
                **(
                    dict(scope_mode="reviewed-overlap", scope_overlaps=[mapping()])
                    if reviewed
                    else {}
                )
            )
            result = engine.calculate(rule, population(rows, historical=history))
            key = ("period" if history else "point") + (
                "_reviewed_overlap" if reviewed else "_exact"
            )
            assert result["count"] == manifest["expected_counts"][key]
            if result["count"]:
                interval = result["conflict_intervals"][0]
                assert {
                    key: interval[key] for key in ("conflict_from", "conflict_through")
                } == manifest["expected_overlap_interval"]
