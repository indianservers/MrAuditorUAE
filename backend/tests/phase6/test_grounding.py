import uuid

import pytest

from app.api.v1.tax_ai import validate_grounding
from app.modules.tax.ai_output import TaxAIOutput


def output():
    return TaxAIOutput.model_validate(
        {
            "issue": "Synthetic entertainment review",
            "relevant_facts": ["Supplied expense"],
            "applicable_legislation": [
                {
                    "rule_record_id": str(uuid.UUID(int=1)),
                    "source_id": "CT-LAW",
                    "article": "29",
                    "rule_version": 1,
                }
            ],
            "tax_period": "2026-01-01/2026-12-31",
            "analysis": "Review Article29 facts",
            "potential_treatment": "Human review required",
            "missing_facts": [],
            "uncertainties": ["Verify facts"],
            "supporting_references": [str(uuid.UUID(int=2))],
            "required_human_action": "Check recipient scope",
            "requires_human_review": True,
            "tax_position_approved": False,
        }
    )


def test_grounded_tax_output_and_forged_citations():
    value = output()
    payload = {
        "legal_references": [value.applicable_legislation[0].model_dump(mode="json")],
        "evidence_ids": [str(uuid.UUID(int=2))],
        "tax_period": value.tax_period,
    }
    validate_grounding(value, payload)
    for key, replacement in [
        ("tax_period", "2025"),
        ("analysis", "Under Article 999 deduction is approved"),
        ("supporting_references", [uuid.UUID(int=99)]),
    ]:
        changed = value.model_copy(update={key: replacement})
        with pytest.raises(ValueError):
            validate_grounding(changed, payload)
