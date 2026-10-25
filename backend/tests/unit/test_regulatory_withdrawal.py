import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from app.modules.regulatory import service
from app.modules.regulatory.schemas import Decision, Rule
from tests.unit.test_regulatory_evaluation import fixture


@pytest.mark.parametrize("reason", ["", " " * 20, "  short  "])
def test_withdrawal_requires_meaningful_reason(reason):
    with pytest.raises(ValidationError):
        Decision(action="withdraw", expected_sequence=1, comments=reason)


async def test_controlled_revert_normalizes_new_optional_fields_without_rewriting_old_body(
    monkeypatch,
):
    old_body = fixture().model_dump(mode="json")
    for field in ("benefit_parameters", "payroll_parameters"):
        old_body.pop(field, None)
    prior = SimpleNamespace(rule_key=old_body["rule_key"], body=old_body)
    monkeypatch.setattr(service, "get", AsyncMock(return_value=prior))
    monkeypatch.setattr(service, "authorize", AsyncMock())
    monkeypatch.setattr(service, "lock", AsyncMock())
    monkeypatch.setattr(service, "sequence", AsyncMock(return_value=0))
    monkeypatch.setattr(service, "action", AsyncMock())
    db = SimpleNamespace(scalar=AsyncMock(return_value=1), add=Mock(), flush=AsyncMock())
    ctx = SimpleNamespace(tenant_id=uuid.uuid4(), user_id=uuid.uuid4())
    restored = await service.propose(
        db,
        ctx,
        Rule.model_validate({**old_body, "reverts_version_id": str(uuid.uuid4())}),
        "synthetic-request",
    )
    assert restored.body["benefit_parameters"] is None
    assert restored.body["payroll_parameters"] is None
    assert "benefit_parameters" not in old_body and "payroll_parameters" not in old_body
