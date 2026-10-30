"""Approved filing scope cannot migrate between jurisdictions without reassessment."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.grc import filing, schemas


@pytest.mark.parametrize("country", ["AE", "IN"])
@pytest.mark.parametrize("stage", ["approved_for_submission", "submitted", "acknowledged"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("jurisdiction", "IN"),
        ("module", "vat"),
        ("source_url", "https://synthetic.invalid/replacement-rule"),
        ("effective_from", "2026-04-01"),
        ("deadline_kind", "client_agreed"),
        ("required_evidence", "Changed evidence criteria"),
        ("compliance_assessment", "exception"),
        ("owner_id", None),
        ("entity_id", None),
        ("evidence_ids", [str(uuid4())]),
        ("statutory_record_id", str(uuid4())),
        ("submission_evidence_id", str(uuid4())),
        ("acknowledgment_evidence_id", str(uuid4())),
    ],
)
async def test_approved_scope_change_requires_preparing(monkeypatch, stage, field, value, country):
    owner, reviewer = uuid4(), uuid4()
    original = schemas.Obligation.model_validate(
        {
            "owner_id": str(owner),
            "entity_id": str(uuid4()),
            "module": "policy",
            "source_url": "https://synthetic.invalid/rule",
            "jurisdiction": country,
            "effective_from": "2026-01-01",
            "deadline": "2026-12-31",
            "deadline_kind": "firm_internal",
            "required_evidence": "Independent scope evidence",
            "compliance_assessment": "pending",
            "reviewer_id": str(reviewer),
            "readiness_evidence_ids": [str(uuid4())],
            "filing_stage": stage,
            "submission_evidence_id": str(uuid4())
            if stage != "approved_for_submission" or field == "submission_evidence_id"
            else None,
            "acknowledgment_evidence_id": str(uuid4())
            if stage == "acknowledged" or field == "acknowledgment_evidence_id"
            else None,
        }
    )
    previous = SimpleNamespace(body=original.model_dump(mode="json"), status="REVISED")

    async def record(*args):
        return previous if args[3] == record_id else SimpleNamespace(kind="evidence")

    record_id = uuid4()
    monkeypatch.setattr(filing.audit, "get_record", record)
    monkeypatch.setattr(filing, "engagement_permissions", AsyncMock())
    payload = original.model_dump(mode="json")
    payload[field] = (
        str(uuid4())
        if field in {"owner_id", "entity_id"}
        else ("IN" if country == "AE" else "AE")
        if field == "jurisdiction"
        else value
    )
    changed = schemas.Obligation.model_validate(payload)
    with pytest.raises(HTTPException, match="Approved filing inputs changed") as error:
        await filing.validate_transition(
            None,
            SimpleNamespace(user_id=reviewer, tenant_id=uuid4()),
            SimpleNamespace(id=uuid4()),
            changed,
            record_id,
        )
    assert error.value.status_code == 409
    # A deliberate return to preparing permits changed facts and requires a new review cycle.
    payload["filing_stage"] = "preparing"
    await filing.validate_transition(
        None,
        SimpleNamespace(user_id=reviewer, tenant_id=uuid4()),
        SimpleNamespace(id=uuid4()),
        schemas.Obligation.model_validate(payload),
        record_id,
    )
