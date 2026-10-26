from decimal import Decimal

import pytest

from app.modules.country_workflows.review import approval_error
from tests.unit.test_shared_audit_workflows import run


def subject(**changes):
    return {
        "id": "SUBJECT-1",
        "risk": "high",
        "pep": False,
        "identity_verified": True,
        "reviewed_on": "2026-01-01",
        "review_due": "2026-12-31",
        "identity_expires": "2027-01-01",
        "identity_evidence": "ID-1",
        "source_of_funds_evidence": "SOF-1",
        "source_of_wealth_evidence": "SOW-1",
        "senior_approval_evidence": "APPROVAL-1",
        **changes,
    }


def test_kyc_high_risk_evidence_and_expiry_are_hard_blocks():
    assert run("kyc-edd-review", {"subjects": [subject()]})["exception_count"] == 0
    output = run(
        "kyc-edd-review",
        {"subjects": [subject(source_of_funds_evidence="", identity_expires="2026-06-01")]},
    )
    assert output["blocked"]
    assert set(output["rows"][0]["exceptions"]) == {
        "IDENTITY_EXPIRED",
        "MISSING_SOURCE_OF_FUNDS_EVIDENCE",
    }


def edge(company, owner, fraction, owner_kind="person", **changes):
    return {
        "id": company + ":" + owner,
        "company": company,
        "owner": owner,
        "owner_kind": owner_kind,
        "fraction": fraction,
        "effective_from": "2026-01-01",
        "evidence_reference": "OWNERSHIP-1",
        **changes,
    }


def policy(**changes):
    return {
        "id": "POLICY-1",
        "country": "AE",
        "threshold": "0.25",
        "comparison": "greater-than",
        "effective_from": "2026-01-01",
        "effective_to": "2026-12-31",
        "evidence_reference": "SYNTHETIC-REVIEWED-THRESHOLD",
        **changes,
    }


def test_indirect_and_direct_paths_accumulate_without_inventing_ubo_law():
    output = run(
        "ownership-lookthrough",
        {
            "ownership": [
                edge("A", "B", "0.5", "company"),
                edge("A", "P1", "0.5"),
                edge("B", "P1", "0.5"),
                edge("B", "P2", "0.5"),
            ],
            "policy": [policy()],
        },
        subjects=["A"],
    )
    assert not output["blocked"]
    values = {r["person_id"]: r for r in output["rows"]}
    assert Decimal(values["P1"]["economic_fraction"]) == Decimal("0.75")
    assert Decimal(values["P2"]["economic_fraction"]) == Decimal("0.25")
    assert values["P1"]["threshold_candidate"] and not values["P2"]["threshold_candidate"]


def test_ownership_cycle_incomplete_population_and_wrong_policy_block():
    for edges in [
        [edge("A", "B", "1", "company"), edge("B", "A", "1", "company")],
        [edge("A", "P1", "0.5")],
    ]:
        assert run(
            "ownership-lookthrough", {"ownership": edges, "policy": [policy()]}, subjects=["A"]
        )["blocked"]
    output = run(
        "ownership-lookthrough",
        {"ownership": [edge("A", "P1", "1")], "policy": [policy(country="IN")]},
        subjects=["A"],
    )
    assert output["blocked"]


def screening_sources(name="شركة الاختبار", list_name="شركة الاختبار", **changes):
    return {
        "subjects": [{"id": "SUBJECT-1", "name": name, "evidence_reference": "SUBJECT-EVIDENCE"}],
        "list": [
            {
                "id": "ENTRY-1",
                "list_subject_id": "LIST-PERSON-1",
                "name": list_name,
                "list_version": "SYNTHETIC-LIST-1",
                "published_on": "2026-06-29",
                "evidence_reference": "RETAINED-LIST-EVIDENCE",
                **changes,
            }
        ],
        "policy": [
            {
                "id": "POLICY-1",
                "minimum_similarity": "0.9",
                "maximum_list_age_days": 7,
                "list_version": "SYNTHETIC-LIST-1",
                "evidence_reference": "SCREENING-POLICY",
            }
        ],
    }


def test_unicode_name_match_is_explicit_baseline_never_a_probability_or_clearance():
    output = run("sanctions-name-review", screening_sources())
    row = output["rows"][0]
    assert output["screening_execution_mode"] == "rules_baseline"
    assert row["state"] == "POTENTIAL_NAME_MATCH"
    assert row["candidates"][0]["name_similarity"] == 1
    assert row["reviewer_disposition"] == "UNREVIEWED"
    unmatched = run("sanctions-name-review", screening_sources(name="Unrelated unrelated firm"))
    assert unmatched["rows"][0]["state"] == "NO_NAME_MATCH_REQUIRES_REVIEW"


def test_empty_stale_or_wrong_version_list_does_not_clear_anyone():
    for changed in [
        {"published_on": "2026-01-01"},
        {"published_on": "2026-07-01"},
        {"list_version": "OLD-LIST"},
    ]:
        output = run("sanctions-name-review", screening_sources(**changed))
        assert (
            output["blocked"]
            and output["rows"][0]["state"] == "SCREENING_LIST_STALE_OR_WRONG_VERSION"
        )
    sources = screening_sources()
    sources["list"] = []
    output = run("sanctions-name-review", sources)
    assert output["blocked"] and output["rows"][0]["state"] == "SCREENING_LIST_UNAVAILABLE"


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_all_screening_candidates_retained_with_source_context(country):
    sources = screening_sources()
    entry = sources["list"][0]
    sources["list"] = [{**entry, "id": f"ENTRY-{index:04d}", "list_subject_id": f"PERSON-{index:04d}"} for index in reversed(range(121))]
    output = run("sanctions-name-review", sources, country=country)
    row = output["rows"][0]
    assert output["candidate_retention_contract"] == "complete-screening-candidates/1"
    assert row["subject_name"] == sources["subjects"][0]["name"]
    assert row["subject_evidence_reference"] == "SUBJECT-EVIDENCE"
    assert row["candidate_count"] == len(row["candidates"]) == 121
    assert not row["candidate_preview_truncated"]
    assert [hit["source_id"] for hit in row["candidates"]] == [f"ENTRY-{index:04d}" for index in range(121)]
    assert row["candidates"][-1] == {"source_id": "ENTRY-0120", "list_subject_id": "PERSON-0120", "list_name": entry["name"], "list_version": entry["list_version"], "published_on": entry["published_on"], "evidence_reference": entry["evidence_reference"], "name_similarity": 1.0}
    assert row["reviewer_disposition"] == "UNREVIEWED"


def test_maximum_screening_comparison_population_is_complete_and_excess_rejected():
    sources = screening_sources(name="SYNTHETIC NAME", list_name="SYNTHETIC NAME")
    sources["subjects"] = [{**sources["subjects"][0], "id": f"SUBJECT-{index}"} for index in range(20)]
    sources["list"] = [{**sources["list"][0], "id": f"ENTRY-{index:04d}"} for index in range(5000)]
    output = run("sanctions-name-review", sources)
    assert sum(len(row["candidates"]) for row in output["rows"]) == 100000
    assert all(row["candidate_count"] == 5000 and not row["candidate_preview_truncated"] for row in output["rows"])
    sources["subjects"].append({**sources["subjects"][0], "id": "EXCESS"})
    with pytest.raises(ValueError, match="comparison bound"):
        run("sanctions-name-review", sources)


@pytest.mark.parametrize("truncated_flag", [True, False])
def test_documented_dispositions_cannot_approve_incomplete_candidate_retention(truncated_flag):
    output = run("sanctions-name-review", screening_sources())
    row = output["rows"][0]
    row["auditor_status"] = "EXCEPTION_DOCUMENTED"
    assert approval_error(output) is None
    row.update(candidate_count=121, candidate_preview_truncated=truncated_flag)
    assert "complete retained candidates" in approval_error(output)
