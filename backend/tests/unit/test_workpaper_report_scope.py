"""Report authors cannot invent coverage absent from a reviewed workpaper declaration."""

import uuid
from copy import deepcopy

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.audit_execution.schemas import WorkingPaper
from app.modules.regulatory.schemas import ReportBlock, ReportTemplate
from app.modules.regulatory.workpaper_report_scope import require_mapping
from tests.unit.test_form26_index import config

ID = str(uuid.uuid4())


def paper(key="form26.C.1"):
    return dict(
        folder="SYNTHETIC item support",
        sections=[
            {
                "heading": "Reviewed source facts",
                "text": "Synthetic source facts and explicit mapping assessment",
            }
        ],
        sources=[{"kind": "record", "id": ID}],
        conclusion="Synthetic mechanical coverage only, not a legal conclusion",
        report_requirement_scope={
            "preset_id": "india-form26-index:A/1",
            "period_start": "2026-04-01",
            "period_end": "2027-03-31",
            "items": [
                {
                    "key": key,
                    "disposition": "REQUIRED",
                    "section_index": 0,
                    "supporting_sources": [{"kind": "record", "id": ID}],
                    "assessment": "Synthetic explicit item support against source and section",
                }
            ],
        },
    )


def report(key="form26.C.1"):
    data = config()
    next(r for r in data["requirements"] if r["key"] == key)["disposition"] = "REQUIRED"
    return ReportTemplate.model_validate(data), ReportBlock(
        key="item",
        title="Mapped item",
        kind="working_paper_reference",
        source_kind="record",
        source_id=str(uuid.uuid4()),
        requirement_keys=[key],
    )


def test_exact_reviewed_declaration_is_consumable_without_changing_its_content():
    body = WorkingPaper.model_validate(paper()).model_dump(mode="json")
    original = deepcopy(body)
    require_mapping(*report(), body)
    assert body == original


@pytest.mark.parametrize(
    "fault",
    [
        "section",
        "empty-section",
        "unlinked-source",
        "wrong-source-kind",
        "duplicate-item",
        "duplicate-link",
        "unknown-item",
        "legacy-period",
    ],
)
def test_invalid_declarations_cannot_be_saved_in_a_workpaper(fault):
    body = paper()
    scope = body["report_requirement_scope"]
    item = scope["items"][0]
    if fault == "section":
        item["section_index"] = 1
    elif fault == "empty-section":
        body["sections"][0]["text"] = "   "
    elif fault == "unlinked-source":
        item["supporting_sources"][0]["id"] = str(uuid.uuid4())
    elif fault == "wrong-source-kind":
        item["supporting_sources"][0]["kind"] = "intelligence"
    elif fault == "duplicate-item":
        scope["items"] *= 2
    elif fault == "duplicate-link":
        item["supporting_sources"] *= 2
    elif fault == "unknown-item":
        item["key"] = "form26.D.999"
    else:
        scope.update(period_start="2025-04-01", period_end="2026-03-31")
    with pytest.raises(ValidationError):
        WorkingPaper.model_validate(body)


@pytest.mark.parametrize(
    "fault", ["missing", "wrong-period", "wrong-part", "unmapped-item", "applicability"]
)
def test_report_scope_and_item_state_must_match_the_workpaper(fault):
    key = "form26.schedule.gst"
    body = paper(key)
    scope = body["report_requirement_scope"]
    if fault == "missing":
        body.pop("report_requirement_scope")
    elif fault == "wrong-period":
        scope["period_start"] = "2026-05-01"
    elif fault == "wrong-part":
        scope["preset_id"] = "india-form26-index:B/1"
    elif fault == "unmapped-item":
        scope["items"][0]["key"] = "form26.C.1"
    else:
        scope["items"][0]["disposition"] = "NOT_APPLICABLE"
    with pytest.raises(HTTPException) as error:
        require_mapping(*report(key), body)
    assert error.value.status_code == 409
