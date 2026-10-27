from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.modules.regulatory.report_requirements import (
    CONTRACT,
    coverage,
    current_contract,
    implementation_hash,
)
from app.modules.regulatory.schemas import ReportTemplate

U = "00000000-0000-4000-8000-000000000001"


def config(**changes):
    base = {
        "title": "SYNTHETIC report",
        "category": "management-letter",
        "rationale": "Synthetic source scope review",
        "requirements": [
            {
                "key": "one",
                "title": "Source presentation",
                "disposition": "REQUIRED",
                "source_required": True,
                "basis": "Synthetic explicit source requirement",
            }
        ],
        "requirements_assessed": True,
        "requirements_basis": "Synthetic declared scope; not a statutory manifest",
        "blocks": [
            {
                "key": "source",
                "title": "Source table",
                "kind": "financial_table",
                "source_kind": "intelligence",
                "source_id": U,
                "requirement_keys": ["one"],
            }
        ],
    }
    return ReportTemplate.model_validate(base | changes)


def test_source_linked_declared_scope_is_not_a_legal_completeness_claim():
    result = coverage(config())
    assert result["complete"] and result["items"][0]["block_keys"] == ["source"]
    assert result["source_validation"] == "RECHECK_BEFORE_REVIEW_OR_GENERATION"
    assert result["statutory_completeness_qualified"] is False


@pytest.mark.parametrize(
    "fault",
    [
        "unassessed-scope",
        "empty-scope",
        "unassessed-item",
        "unmapped",
        "source-missing",
        "not-applicable-without-source",
        "basis-missing",
    ],
)
def test_incomplete_declared_scope_remains_unready(fault):
    raw = config().model_dump(mode="json")
    if fault == "unassessed-scope":
        raw["requirements_assessed"] = False
    elif fault == "empty-scope":
        raw["requirements"] = []
        raw["blocks"][0]["requirement_keys"] = []
    elif fault == "unassessed-item":
        raw["requirements"][0]["disposition"] = "UNASSESSED"
    elif fault == "unmapped":
        raw["blocks"][0]["requirement_keys"] = []
    elif fault == "basis-missing":
        raw["requirements_basis"] = ""
    else:
        raw["blocks"] = [
            {
                "key": "note",
                "title": "Authored note",
                "kind": "narrative",
                "text": "Synthetic authored narrative is not source evidence",
                "requirement_keys": ["one"],
            }
        ]
        if fault == "not-applicable-without-source":
            raw["requirements"][0].update(disposition="NOT_APPLICABLE", source_required=False)
    assert not coverage(ReportTemplate.model_validate(raw))["complete"]


def test_authored_narrative_requirement_is_explicit_and_not_an_evidence_substitute():
    raw = config().model_dump(mode="json")
    raw["requirements"][0]["source_required"] = False
    raw["blocks"] = [
        {
            "key": "note",
            "title": "Authored statement",
            "kind": "narrative",
            "text": "Synthetic management communication text",
            "requirement_keys": ["one"],
        }
    ]
    assert coverage(ReportTemplate.model_validate(raw))["complete"]


@pytest.mark.parametrize(
    "fault", ["duplicate-requirement", "unknown-reference", "duplicate-reference"]
)
def test_invalid_mapping_is_not_silently_accepted(fault):
    raw = config().model_dump(mode="json")
    if fault == "duplicate-requirement":
        raw["requirements"] *= 2
    elif fault == "unknown-reference":
        raw["blocks"][0]["requirement_keys"] = ["absent"]
    else:
        raw["blocks"][0]["requirement_keys"] = ["one", "one"]
    with pytest.raises(ValidationError):
        ReportTemplate.model_validate(raw)


def test_legacy_or_changed_implementation_is_stale_without_rewriting_history():
    body = {"title": "Legacy approved template"}
    before = deepcopy(body)
    assert not current_contract(body) and body == before
    body.update(
        report_requirements_contract=CONTRACT,
        report_requirements_implementation=implementation_hash(),
    )
    assert current_contract(body)
    body["report_requirements_implementation"] = "outdated"
    assert not current_contract(body)
