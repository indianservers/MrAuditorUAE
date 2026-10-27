import uuid
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


@pytest.mark.parametrize("record", [False, True])
def test_report_preparers_preserve_authors_without_conflating_event_reviewer(record):
    from types import SimpleNamespace

    from app.modules.regulatory.report_requirements import preparers

    source = SimpleNamespace(
        body={"contributors": ["source-author", "source-author"]}, created_by="latest-creator"
    )
    expected = {"source-author", "latest-creator"} if record else {"source-author"}
    assert preparers(source, record=record) == expected
    source.body = {}
    assert preparers(source, record=record) == {"latest-creator"}


def test_old_requirements_contract_does_not_preserve_incomplete_author_provenance():
    body = {
        "report_requirements_contract": "declared-report-requirements/1",
        "report_requirements_implementation": implementation_hash(),
    }
    assert not current_contract(body)


@pytest.mark.parametrize("changed", ["report_requirements.py", "reporting.py", "schemas.py"])
def test_implementation_contract_tracks_all_report_semantics(monkeypatch, changed):
    from pathlib import Path

    original = Path.read_bytes
    before = implementation_hash()
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda path: original(path) + (b" changed" if path.name == changed else b""),
    )
    assert implementation_hash() != before


@pytest.mark.asyncio
async def test_audit_record_preparers_include_all_immutable_editor_snapshots():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from app.modules.regulatory.report_requirements import record_preparers

    db = SimpleNamespace(
        scalars=AsyncMock(
            return_value=Mock(all=Mock(return_value=["older-editor", "latest-editor", None]))
        )
    )
    source = SimpleNamespace(
        id=uuid.uuid4(), body={}, created_by="original-author", prepared_by="latest-editor"
    )
    result = await record_preparers(db, SimpleNamespace(tenant_id=uuid.uuid4()), source)
    assert result == {"original-author", "older-editor", "latest-editor"}
