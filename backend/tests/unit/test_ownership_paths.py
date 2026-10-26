"""Retained exact economic paths and explicit partial-graph evidence."""

from decimal import Decimal
from fractions import Fraction

import pytest

from app.modules.country_workflows.review import approval_error
from tests.unit.test_diligence_audit_workflows import edge, policy
from tests.unit.test_shared_audit_workflows import run


def population(country="AE"):
    return {
        "ownership": [
            edge("A", "B", "0.5", "company"),
            edge("A", "P1", "0.5"),
            edge("B", "P1", "0.5"),
            edge("B", "P2", "0.5"),
        ],
        "policy": [policy(country=country)],
    }


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_each_economic_path_retains_every_original_edge_and_reference(country):
    result = run("ownership-lookthrough", population(country), subjects=["A"], country=country)
    assert (
        not result["blocked"] and result["ownership_path_contract"] == "economic-ownership-paths/1"
    )
    paths = result["ownership_paths"]
    assert len(paths) == 3 and len(result["ownership_path_steps"]) == 5
    p1 = next(row for row in result["rows"] if row["person_id"] == "P1")
    assert p1["economic_fraction"] == "0.75" and p1["path_count"] == 2
    assert {path["path_id"] for path in paths if path["person_id"] == "P1"} == set(
        p1["ownership_path_ids"]
    )
    indirect = next(path for path in paths if path["edge_count"] == 2 and path["person_id"] == "P1")
    assert indirect["company_owner_chain"] == ["A", "B", "P1"]
    assert indirect["edge_source_ids"] == ["A:B", "B:P1"]
    assert all(
        step["evidence_reference"] == "OWNERSHIP-1" for step in result["ownership_path_steps"]
    )
    assert result["ownership_scope"]["country"] == country


def test_incomplete_graph_retains_partial_paths_without_a_complete_threshold_decision():
    rows = {
        "ownership": [edge("A", "P1", "0.25"), edge("A", "MISSING", "0.5", "company")],
        "policy": [policy(comparison="at-least")],
    }
    result = run("ownership-lookthrough", rows, subjects=["A"])
    assert result["blocked"]
    person = next(row for row in result["rows"] if row.get("person_id") == "P1")
    assert person["economic_fraction"] == "0.25"
    assert person["threshold_candidate"] is None and person["observed_threshold_reached"] is True
    assert person["fraction_scope"] == "INCOMPLETE_GRAPH_PARTIAL_PATHS"
    assert person["state"] == "OWNERSHIP_EVIDENCE_GAPS"
    gaps = [path for path in result["ownership_paths"] if path["kind"] == "graph-gap"]
    assert {path["gap_reason"] for path in gaps} == {
        "OWNERSHIP_POPULATION_NOT_COMPLETE",
        "CORPORATE_OWNER_EVIDENCE_MISSING",
    }
    missing = next(path for path in gaps if path["gap_at_company"] == "MISSING")
    assert missing["economic_fraction"] is None and missing["reach_fraction"] == "0.5"
    assert missing["edge_source_ids"] == ["A:MISSING"]
    for row in result["rows"]:
        row["auditor_status"] = "EXCEPTION_DOCUMENTED"
    assert approval_error(result)


def test_cycle_and_duplicate_failures_retain_the_actual_failed_path():
    rows = {
        "ownership": [edge("A", "B", "1", "company"), edge("B", "A", "1", "company")],
        "policy": [policy()],
    }
    result = run("ownership-lookthrough", rows, subjects=["A"])
    gap = result["ownership_paths"][0]
    assert gap["gap_reason"] == "OWNERSHIP_CYCLE_REQUIRES_ASSESSMENT"
    assert gap["company_owner_chain"] == ["A", "B", "A"]
    assert gap["edge_source_ids"] == ["A:B", "B:A"]
    rows["ownership"] = [edge("A", "P1", "0.5"), edge("A", "P1", "0.5", id="DUPLICATE")]
    result = run("ownership-lookthrough", rows, subjects=["A"])
    gap = next(path for path in result["ownership_paths"] if path["kind"] == "graph-gap")
    assert gap["edge_source_ids"] == ["DUPLICATE"] and result["blocked"]


def test_exact_deep_shares_do_not_round_up_to_a_policy_threshold():
    edges = [edge("A", "B0", "0.25", "company"), edge("A", "OTHER", "0.75")]
    for i in range(18):
        edges.extend(
            [
                edge(f"B{i}", "P1", "0.9999999999"),
                edge(f"B{i}", f"B{i + 1}", "0.0000000001", "company"),
            ]
        )
    edges.append(edge("B18", "OTHER", "1"))
    result = run(
        "ownership-lookthrough",
        {"ownership": edges, "policy": [policy(comparison="at-least")]},
        subjects=["A"],
    )
    row = next(row for row in result["rows"] if row["person_id"] == "P1")
    assert Fraction(Decimal(row["economic_fraction"])) == Fraction(1, 4) * (
        1 - Fraction(1, 10**180)
    )
    assert row["threshold_candidate"] is False and not result["blocked"]
    assert max(path["edge_count"] for path in result["ownership_paths"]) == 20


@pytest.mark.parametrize("subjects", [["A", "A"], [" A"], [" "]])
def test_subject_identifiers_are_explicit_exact_and_distinct(subjects):
    with pytest.raises(ValueError, match="distinct exact nonblank"):
        run("ownership-lookthrough", population(), subjects=subjects)


def test_person_id_cannot_be_selected_as_a_company_subject():
    with pytest.raises(ValueError, match="known natural-person"):
        run("ownership-lookthrough", population(), subjects=["P1"])


def test_inactive_edges_do_not_enter_current_paths_and_policy_is_country_and_date_scoped():
    rows = population()
    rows["ownership"].append(edge("A", "OLD", "1", effective_to="2026-01-02"))
    result = run("ownership-lookthrough", rows, subjects=["A"])
    assert result["ownership_scope"]["inactive_edges"] == 1
    assert all("OLD" not in path["company_owner_chain"] for path in result["ownership_paths"])
    rows["policy"][0]["country"] = "IN"
    result = run("ownership-lookthrough", rows, subjects=["A"])
    assert result["blocked"] and result["ownership_paths"] == []


def test_historical_untraceable_results_require_regeneration_before_approval():
    assert approval_error({"workflow": "ownership-lookthrough", "rows": [], "blocked": False})


def test_maximum_source_graph_retains_shared_paths_without_truncation():
    count = 4998
    edges = [edge("R1", "HOLD", "1", "company"), edge("R2", "HOLD", "1", "company")]
    edges.extend(edge("HOLD", f"P{i:04d}", "0.0002") for i in range(count - 1))
    edges.append(edge("HOLD", f"P{count - 1:04d}", "0.0006"))
    result = run(
        "ownership-lookthrough", {"ownership": edges, "policy": [policy()]}, subjects=["R1", "R2"]
    )
    assert not result["blocked"] and len(edges) == 5000
    assert len(result["ownership_paths"]) == 9996 and len(result["ownership_path_steps"]) == 19992
    assert result["ownership_scope"]["explored_transitions"] == 9998
    assert result["ownership_path_steps"][-1]["edge_source_id"] == "HOLD:P4997"


def test_global_traversal_and_retained_step_bounds_fail_instead_of_truncating(monkeypatch):
    from app.modules.country_workflows import ownership_paths

    monkeypatch.setattr(ownership_paths, "MAX_TRANSITIONS", 4)
    with pytest.raises(ValueError, match="bound exceeded"):
        run("ownership-lookthrough", population(), subjects=["A", "B"])
    monkeypatch.setattr(ownership_paths, "MAX_TRANSITIONS", 10000)
    monkeypatch.setattr(ownership_paths, "MAX_PATH_STEPS", 4)
    with pytest.raises(ValueError, match="bound exceeded"):
        run("ownership-lookthrough", population(), subjects=["A"])
