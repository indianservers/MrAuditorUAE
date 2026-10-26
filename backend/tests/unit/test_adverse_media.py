import copy
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.adverse_media import ROLES, ROW_TYPES, compare, documents
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
from app.modules.country_workflows.sources import parse_csv


def packet(country="AE", case="collision"):
    binding = dict(
        source_evidence_version_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "SYNTHETIC media")),
        source_sha256="a" * 64,
    )
    rows = dict(
        subjects=[
            dict(
                id="V1",
                name="SYNTHETIC Example Trading",
                country=country,
                identifiers="Fictional register SYN-123; identity not authenticated",
                assessment="Synthetic subject identifiers independently assessed",
                **binding,
            )
        ],
        searches=[
            dict(
                id="Q1",
                subject_id="V1",
                provider="SYNTHETIC provider",
                query="Example Trading SYN-123",
                aliases_and_identifiers="Example Trading; fictional registration SYN-123",
                queried_on="2026-06-29",
                coverage_from="2025-01-01",
                coverage_through="2026-06-28",
                status="completed",
                expected_mentions=1,
                licence_reference="SYN-LICENCE-1",
                assessment="Synthetic uploaded search receipt with declared coverage",
                **binding,
            )
        ],
        mentions=[
            dict(
                id="M1",
                search_id="Q1",
                article_id="ARTICLE-1",
                publisher="Synthetic publication",
                url="https://example.invalid/synthetic/article-1",
                title="SYNTHETIC unrelated company mention",
                published_on="2026-06-20",
                retrieved_on="2026-06-29",
                identity_status="different-subject",
                identity_rationale="The fictional registration and jurisdiction differ",
                identity_evidence_version_id=binding["source_evidence_version_id"],
                identity_source_sha256=binding["source_sha256"],
                reported_stage="allegation",
                risk="low",
                risk_rationale="Human assessment: fictional identity collision only",
                disposition="no-action",
                reviewed_on="2026-06-30",
                followup_on=None,
                **binding,
            )
        ],
        policy=[
            dict(
                id="P1",
                country=country,
                effective_from="2026-01-01",
                effective_to="2026-12-31",
                coverage_from="2025-01-01",
                coverage_through="2026-06-28",
                maximum_query_age_days=7,
                expected_subjects=1,
                assessment="Synthetic reviewed provider, scope and revalidation policy",
                **binding,
            )
        ],
    )
    if case in {"nil", "unavailable"}:
        rows["mentions"] = []
        rows["searches"][0]["expected_mentions"] = 0
        if case == "unavailable":
            rows["searches"][0]["status"] = "unavailable"
    if case in {"same-subject", "unresolved"}:
        rows["mentions"][0].update(
            identity_status=case,
            identity_rationale="Fictional registration SYN-123 agrees with retained subject evidence"
            if case == "same-subject"
            else "Name overlaps but the article has no verified registration; identity remains unresolved",
            title="SYNTHETIC allegation requiring human review",
            risk="medium",
            risk_rationale="Human assessment of a reported allegation; no legal fact is authenticated"
            if case == "same-subject"
            else "Provisional human triage assessment pending additional identity evidence",
            disposition="escalate",
            followup_on="2026-07-15",
        )
    return normalize(rows)


def normalize(tables):
    return {
        role: [ROW_TYPES[kind].model_validate(row).model_dump(mode="json") for row in tables[role]]
        for role, kind in ROLES.items()
    }


def run(tables=None, country="AE"):
    return compare(
        SimpleNamespace(as_of=date(2026, 6, 30)),
        tables if tables is not None else packet(country),
        country,
    )


@pytest.mark.parametrize("country", ["AE", "IN"])
@pytest.mark.parametrize("case", ["collision", "nil", "same-subject", "unresolved", "unavailable"])
def test_country_media_outcomes(country, case):
    result = run(packet(country, case), country)
    assert result["blocked"] == (case in {"unresolved", "unavailable"})
    assert result["media_review_contract"] == "retained-adverse-media/1"
    assert not result["identity_authenticity_established"]
    assert not result["media_clearance_issued"] and not result["automatic_rejection"]
    if case == "same-subject":
        mention = next(row for row in result["rows"] if row["kind"] == "media-mention")
        assert mention["state"] == "ADVERSE_MENTION_REVIEW"
        assert mention["reported_stage"] == "allegation"
    if case == "nil":
        search = next(row for row in result["rows"] if row["kind"] == "search-control")
        assert search["observed_mentions"] == 0
        assert search["outcome"] == "NO_MENTIONS_REPORTED_NOT_CLEARANCE"


@pytest.mark.parametrize(
    "role,field,value,reason",
    [
        ("searches", "expected_mentions", 2, "MENTION_COUNT_GAP"),
        ("searches", "status", "partial", "SEARCH_PARTIAL"),
        ("searches", "queried_on", "2026-06-01", "SEARCH_STALE_OR_FUTURE"),
        ("searches", "queried_on", "2026-07-01", "SEARCH_STALE_OR_FUTURE"),
        ("searches", "coverage_from", "2026-01-01", "SEARCH_COVERAGE_GAP"),
        ("searches", "subject_id", "UNKNOWN", "UNKNOWN_SUBJECT"),
        ("mentions", "search_id", "UNKNOWN", "UNKNOWN_SEARCH"),
        ("mentions", "published_on", None, "PUBLICATION_DATE_UNKNOWN"),
        ("mentions", "published_on", "2024-01-01", "ARTICLE_OUTSIDE_DECLARED_COVERAGE"),
        ("mentions", "retrieved_on", "2026-06-30", "ARTICLE_RETRIEVED_AFTER_SEARCH"),
        ("mentions", "reviewed_on", "2026-07-01", "REVIEW_AFTER_AS_OF"),
        ("mentions", "risk", "not-assessed", "RISK_ASSESSMENT_MISSING"),
        ("mentions", "disposition", "pending", "DISPOSITION_PENDING"),
        ("mentions", "disposition", "escalate", "IDENTITY_DISPOSITION_CONFLICT"),
        ("mentions", "followup_on", "2026-06-01", "FOLLOWUP_OVERDUE"),
    ],
)
def test_controls_cannot_be_overridden_by_matching_counts(role, field, value, reason):
    tables = packet()
    tables[role][0][field] = value
    result = run(tables)
    assert result["blocked"]
    assert any(reason in row.get("reasons", []) for row in result["rows"])
    result.update(
        workflow="adverse-media-review", media_document_binding="RETAINED_DOCUMENT_BYTES_VERIFIED"
    )
    for row in result["rows"]:
        row["auditor_status"] = "EXCEPTION_DOCUMENTED"
    assert approval_error(result)


def test_missing_subject_search_cannot_look_like_zero_mentions():
    tables = packet()
    tables["searches"] = []
    tables["mentions"] = []
    result = run(tables)
    assert result["blocked"]
    assert result["rows"][-1]["state"] == "SEARCH_MISSING"


def test_foreign_vendor_domicile_does_not_change_engagement_policy_country():
    tables = packet("AE")
    tables["subjects"][0]["country"] = "IN"
    result = run(tables, "AE")
    assert not result["blocked"]
    assert result["media_scope"]["country"] == "AE"
    assert result["rows"][-1]["country"] == "IN"


@pytest.mark.parametrize("value", [True, 1.0, "01", "1.0", "١"])
def test_policy_count_does_not_coerce_ambiguous_integers(value):
    tables = packet()
    tables["policy"][0]["expected_subjects"] = value
    with pytest.raises(ValidationError):
        normalize(tables)


def test_same_subject_monitor_requires_followup_and_remains_observation():
    tables = packet(case="same-subject")
    tables["mentions"][0].update(disposition="monitor", followup_on=None)
    result = run(tables)
    assert result["blocked"]
    assert "FOLLOWUP_DATE_MISSING" in result["rows"][1]["reasons"]


def test_same_url_cannot_be_counted_twice_by_renaming_article_id():
    tables = packet()
    tables["mentions"].append(dict(tables["mentions"][0], id="M2", article_id="RENAMED"))
    with pytest.raises(ValueError, match="once"):
        run(tables)


def test_independent_subject_count_control():
    tables = packet()
    tables["policy"][0]["expected_subjects"] = 2
    result = run(tables)
    assert result["blocked"] and result["rows"][0]["state"] == "SUBJECT_POPULATION_GAP"


def test_positive_identity_requires_documented_exception_disposition():
    result = run(packet(case="same-subject"))
    result.update(
        workflow="adverse-media-review", media_document_binding="RETAINED_DOCUMENT_BYTES_VERIFIED"
    )
    assert "disposition" in approval_error(result)
    for row in result["rows"]:
        row["auditor_status"] = "EXCEPTION_DOCUMENTED"
    assert approval_error(result) is None


@pytest.mark.parametrize("role", ["subjects", "searches", "mentions", "policy"])
def test_duplicate_source_ids_rejected(role):
    tables = packet()
    tables[role].append(copy.deepcopy(tables[role][0]))
    with pytest.raises(ValueError, match="unique IDs"):
        run(tables)


@pytest.mark.parametrize("role", ["searches", "mentions"])
def test_distinct_ids_do_not_hide_duplicate_search_or_article(role):
    tables = packet()
    tables[role].append(dict(tables[role][0], id="duplicate"))
    with pytest.raises(ValueError, match="Duplicate|once"):
        run(tables)


@pytest.mark.parametrize(
    "role,field,value",
    [
        ("policy", "country", "IN"),
        ("policy", "effective_to", "2025-12-31"),
        ("policy", "coverage_through", "2026-07-01"),
    ],
)
def test_wrong_country_or_policy_scope_rejected(role, field, value):
    tables = packet()
    tables[role][0][field] = value
    with pytest.raises(ValueError):
        run(tables)


@pytest.mark.parametrize(
    "field,value",
    [
        ("url", "file:///secret"),
        ("url", "https://user:password@example.invalid"),
        ("retrieved_on", "2026-01-01"),
        ("identity_source_sha256", None),
        ("identity_evidence_version_id", None),
        ("title", " bad title"),
        ("title", "bad\x00title"),
        ("published_on", "2026-06-20T00:00:00Z"),
    ],
)
def test_media_contract_rejects_unsafe_or_implicit_values(field, value):
    tables = packet()
    tables["mentions"][0][field] = value
    with pytest.raises(ValidationError):
        normalize(tables)


@pytest.mark.parametrize("value", [True, 1.0, "01", "١", "1.0"])
def test_mention_count_is_explicit_integer(value):
    tables = packet()
    tables["searches"][0]["expected_mentions"] = value
    with pytest.raises(ValidationError):
        normalize(tables)


def test_full_5000_mentions_retained_without_candidate_truncation():
    tables = packet(case="same-subject")
    tables["mentions"] = [
        dict(
            tables["mentions"][0],
            id=f"M{i}",
            article_id=f"ARTICLE-{i}",
            url=f"https://example.invalid/synthetic/article-{i}",
        )
        for i in range(5000)
    ]
    tables["searches"][0]["expected_mentions"] = 5000
    result = run(tables)
    assert not result["blocked"]
    assert len(result["rows"]) == 5003 and result["exception_count"] == 5000
    assert result["rows"][5000]["article_id"] == "ARTICLE-4999"


def test_documents_include_identity_assessment_and_every_source_binding():
    tables = packet()
    bindings = documents([row for rows in tables.values() for row in rows])
    assert len(bindings) == 5
    assert all(
        set(binding) == {"source_evidence_version_id", "source_sha256"} for binding in bindings
    )
    assert approval_error(dict(workflow="adverse-media-review", rows=[]))


def test_media_source_is_strict_csv_and_uses_count_not_money_controls():
    import csv
    import io

    row = packet()["searches"][0]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    request = SourceInput(
        table_type="media-searches",
        evidence_version_id=uuid.uuid4(),
        label="Synthetic independently controlled media source",
        expected_rows=1,
        control_totals={},
    )
    result = parse_csv(stream.getvalue().encode(), request)
    assert result["rows"][0]["expected_mentions"] == 1
    with pytest.raises(ValueError, match="silently trimmed"):
        parse_csv(
            stream.getvalue().replace("SYNTHETIC provider", " SYNTHETIC provider").encode(), request
        )
    workflow = WorkflowInput(
        workflow="adverse-media-review",
        source_ids={role: uuid.uuid4() for role in ROLES},
        title="Synthetic media comparison",
        rationale="Declared search coverage and human identity review",
        as_of="2026-06-30",
    )
    assert workflow.workflow == "adverse-media-review"


@pytest.mark.parametrize("country", ["AE", "IN"])
@pytest.mark.parametrize("case", ["collision", "nil", "same-subject", "unresolved", "unavailable"])
def test_saved_examples_match_exact_hashes_contracts_and_expected_outcomes(country, case):
    import hashlib
    import json
    from pathlib import Path

    folder = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-adverse-media"
        / country
        / case
    )
    manifest = json.loads((folder / "manifest.json").read_text())
    for name, expected in manifest["sha256"].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected
    tables = {}
    for role, controls in manifest["source_controls"].items():
        request = SourceInput(
            label="Synthetic independently controlled media example",
            evidence_version_id=uuid.uuid4(),
            **controls,
        )
        tables[role] = parse_csv((folder / (role + ".csv")).read_bytes(), request)["rows"]
    result = run(tables, country)
    expected = manifest["expected"]
    for key in ("blocked", "exception_count", "media_clearance_issued", "automatic_rejection"):
        assert result[key] == expected[key]
    assert len(result["rows"]) == expected["result_rows"]
