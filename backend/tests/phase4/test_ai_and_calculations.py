import io
import json
import uuid

import pytest
from pydantic import ValidationError

from app.infrastructure.ai_providers.adapters import MockProvider
from app.modules.ai_engine.schemas import AIRequest
from app.modules.audit_execution.ai_output import AuditAIOutput
from app.modules.audit_execution.catalogue import AI_TASKS
from app.modules.audit_execution.evidence import validate_file
from app.modules.audit_execution.schemas import Materiality
from app.modules.audit_execution.service import materiality


@pytest.mark.parametrize("task", AI_TASKS)
async def test_shared_structured_ai_tasks(task):
    source = uuid.uuid4()
    result = await MockProvider().generate(
        AIRequest(
            task_type="audit_v4_" + task,
            text=json.dumps({"evidence_ids": [str(source)]}),
            model="mock-diagnostic",
            system_prompt="test",
            max_tokens=512,
            request_id="test",
        )
    )
    output = AuditAIOutput.model_validate(result.output)
    assert (
        output.citations == [source] and output.requires_human_review and not output.opinion_issued
    )
    assert not output.evidence_sufficiency_determined and "MOCK" in output.summary


@pytest.mark.parametrize(
    "field", ["requires_human_review", "opinion_issued", "evidence_sufficiency_determined"]
)
def test_ai_cannot_assert_professional_approval(field):
    data = {
        "summary": "draft",
        "observations": [],
        "proposed_procedures": [],
        "missing_information": [],
        "citations": [str(uuid.uuid4())],
        "requires_human_review": True,
        "opinion_issued": False,
        "evidence_sufficiency_determined": False,
    }
    data[field] = not data[field]
    with pytest.raises(ValidationError):
        AuditAIOutput.model_validate(data)


@pytest.mark.parametrize(
    "name,data",
    [
        ("bad.pdf", b"MZ executable"),
        ("bad.png", b"<script>"),
        ("bad.docm", b"ZIP"),
        ("bad.csv", b"<html>script</html>"),
    ],
)
def test_evidence_extension_signature_checks(name, data):
    with pytest.raises(ValueError):
        validate_file(io.BytesIO(data), name)


def test_materiality_decimal_rounding_and_invalid_percentages():
    data = {
        "benchmark": "revenue",
        "benchmark_amount": "100.10",
        "selected_percentage": "5",
        "performance_percentage": "70",
        "trivial_percentage": "5",
        "benchmark_source": "synthetic",
        "rationale": "synthetic",
        "effective_date": "2026-01-01",
    }
    result = materiality(Materiality.model_validate(data))
    assert result["overall"] == "5.01" and result["performance"] == "3.51"
    with pytest.raises(ValidationError):
        Materiality.model_validate({**data, "selected_percentage": "101"})
    with pytest.raises(ValidationError):
        Materiality.model_validate({**data, "trivial_percentage": "80"})
