"""Synthetic parameters test the reusable contract, not UAE legal qualification."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.audit_schemas import BenefitRule
from app.modules.regulatory.benefit_profiles import BenefitParameters
from app.modules.regulatory.evaluation import evaluate
from app.modules.regulatory.schemas import Rule
from app.modules.regulatory.service import validation_blockers


def parameters(**changes):
    return {
        "regime": "SYNTHETIC-REGIME",
        "cohort": "SYNTHETIC-COHORT",
        "work_model": "full-time",
        "minimum_service_years": "1.25",
        "year_days": "360",
        "salary_divisor": "28",
        "first_tier_years": "3",
        "first_tier_days": "18.12345678",
        "later_tier_days": "27",
        "maximum_salary_months": "20",
        **changes,
    }


def profile(**changes):
    return Rule.model_validate(
        {
            "rule_key": "AE-SYNTHETIC-BENEFIT",
            "country": "AE",
            "title": "Synthetic benefit profile",
            "description": "Synthetic parameters without any statutory rate assertion",
            "framework": "IFRS",
            "period_basis": "transaction_date",
            "effective_from": "2026-01-01",
            "effective_to": "2026-12-31",
            "citations": [
                {
                    "authority": "Synthetic authority",
                    "legislation": "Test only",
                    "url": "https://mof.gov.ae/",
                    "paragraph": "SYNTHETIC",
                }
            ],
            "input_requirements": ["employee_service"],
            "output_requirements": ["employee_benefit"],
            "method": "benefit_profile",
            "benefit_parameters": parameters(),
            "amendment_reason": "Synthetic test of reviewed profile representation",
            "expected_sequence": 0,
            **changes,
        }
    )


def test_profile_preserves_exact_engine_parameters_without_inventing_review():
    rule = profile()
    values = rule.benefit_parameters.model_dump(mode="json")
    assert values == parameters()
    canonical = BenefitRule.model_validate(
        {
            **values,
            "id": "SYNTHETIC-ROW",
            "effective_from": rule.effective_from,
            "effective_to": rule.effective_to,
            "evidence_reference": "SYNTHETIC",
            "source_url": "https://mof.gov.ae/",
            "source_version": "SYNTHETIC",
            "source_sha256": "a" * 64,
            "source_evidence_version_id": "00000000-0000-0000-0000-000000000001",
            "applicability_review": "Synthetic reviewed applicability only",
        }
    )
    assert BenefitParameters.model_validate(values).first_tier_days == canonical.first_tier_days
    assert validation_blockers(rule)
    assert rule.professional_review_status == "PENDING"


@pytest.mark.parametrize(
    "changes",
    [
        {"country": "IN", "rule_key": "IN-SYNTHETIC-BENEFIT"},
        {"period_basis": "period_end"},
        {"applicability": [{"field": "entity_type", "operator": "equals", "values": ["company"]}]},
        {"benefit_parameters": None},
        {"benefit_parameters": parameters(work_model="other")},
        {"method": "checklist"},
        {"method": "flat_rate", "rate": "0.1", "input_requirements": ["tax_base"]},
        {"rate": "0.1"},
        {"calculation_currency": "AED"},
        {"benefit_parameters": parameters(year_days="0")},
        {"benefit_parameters": parameters(salary_divisor="32")},
        {"benefit_parameters": parameters(first_tier_days="NaN")},
        {"benefit_parameters": parameters(maximum_salary_months="0")},
        {"benefit_parameters": parameters(first_tier_days="18.123456789")},
    ],
)
def test_invalid_or_misclassified_profiles_rejected(changes):
    with pytest.raises(ValidationError):
        profile(**changes)


@pytest.mark.parametrize("work_model", ["full-time", "part-time"])
def test_generic_evaluation_requires_employee_workflow(work_model):
    outcome = evaluate(
        profile(benefit_parameters=parameters(work_model=work_model)),
        {"tax_base": "1000", "employee_service": True},
        date(2026, 1, 1),
        date(2026, 12, 31),
        date(2026, 6, 30),
    )
    assert outcome["applicability"] == "PENDING"
    assert outcome["required_workflow"] == "uae-benefit-review"
    assert "calculation" not in outcome
