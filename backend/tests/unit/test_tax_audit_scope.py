"""Tax-year cutover and reviewed exact source facts; no filing/form-content claim."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.modules.regulatory.schemas import ReportTemplate
from app.modules.regulatory.tax_forms import IndiaTaxAuditScope, require_assessed_tax_scope

CASE = "00000000-0000-4000-8000-000000000001"


def scope(**changes):
    return IndiaTaxAuditScope.model_validate(
        {
            "applicability_id": CASE,
            "tax_period_start": "2025-04-01",
            "tax_period_end": "2026-03-31",
            "audited_under_other_law": True,
            "form": "3CA-3CD",
            **changes,
        }
    )


def assessed(selected):
    facts = selected.facts()
    return {
        "area": "india-tax-audit",
        "country": "IN",
        "review_status": "REVIEWED",
        "items": [
            {
                "state": "PREPARED",
                "facts": facts,
                "fact_sources": {
                    key: {"kind": "record", "id": CASE, "path": [key], "comparison": "exact"}
                    for key in facts
                },
                "applicability_result": {"applicability": "APPLICABLE"},
                "procedure": "SYNTHETIC retained selection evidence reviewed",
                "conclusion": "SYNTHETIC assessed period and other-law audit basis",
                "evidence_ids": [CASE],
            }
        ],
    }


@pytest.mark.parametrize("other,form,part", [(True, "3CA-3CD", None), (False, "3CB-3CD", None)])
def test_legacy_form_depends_on_period_and_other_law_basis(other, form, part):
    selected = scope(audited_under_other_law=other, form=form, audit_report_part=part)
    require_assessed_tax_scope(selected, assessed(selected))
    assert selected.tax_period_start.year == 2025


@pytest.mark.parametrize("other,part", [(True, "C"), (False, "D")])
def test_modern_form_keeps_audit_report_parts_separate(other, part):
    selected = scope(
        tax_period_start="2026-04-01",
        tax_period_end="2027-03-31",
        audited_under_other_law=other,
        form="26",
        audit_report_part=part,
    )
    require_assessed_tax_scope(selected, assessed(selected))


@pytest.mark.parametrize(
    "changes",
    [
        {"form": "26", "audit_report_part": "C"},
        {"form": "3CB-3CD"},
        {"audit_report_part": "C"},
        {"tax_period_end": "2026-04-01"},
        {"tax_period_end": "2025-03-31"},
        {"audited_under_other_law": "true"},
        {"audited_under_other_law": 1},
        {"tax_period_start": "2026-04-01", "tax_period_end": "2027-03-31"},
        {
            "tax_period_start": "2026-04-01",
            "tax_period_end": "2027-03-31",
            "form": "26",
            "audit_report_part": "D",
        },
    ],
)
def test_wrong_period_part_or_unassessed_boolean_is_rejected(changes):
    with pytest.raises(ValidationError):
        scope(**changes)


def test_stub_period_is_explicit_and_does_not_cross_tax_years():
    assert scope(tax_period_start="2025-11-20").form == "3CA-3CD"
    assert scope(tax_period_start="2026-03-31").form == "3CA-3CD"


@pytest.mark.parametrize(
    "fault",
    [
        "country",
        "area",
        "unreviewed",
        "pending",
        "wrong-period",
        "wrong-form",
        "bool-coercion",
        "missing-binding",
        "numeric-binding",
        "missing-provenance",
        "no-evidence",
        "no-procedure",
    ],
)
def test_scope_cannot_be_cleared_by_unrelated_or_unresolved_source_facts(fault):
    selected = scope()
    body = deepcopy(assessed(selected))
    item = body["items"][0]
    if fault == "country":
        body["country"] = "AE"
    elif fault == "area":
        body["area"] = "caro"
    elif fault == "unreviewed":
        body["review_status"] = "UNVERIFIED"
    elif fault == "pending":
        item["state"] = "PENDING"
    elif fault == "wrong-period":
        item["facts"]["tax_period_start"] = "2026-04-01"
    elif fault == "wrong-form":
        item["facts"]["tax_audit_form"] = "3CB-3CD"
    elif fault == "bool-coercion":
        item["facts"]["audited_under_other_law"] = 1
    elif fault == "missing-binding":
        item["fact_sources"].pop("tax_period_end")
    elif fault == "numeric-binding":
        item["fact_sources"]["tax_period_end"]["comparison"] = "numeric"
    elif fault == "missing-provenance":
        item["applicability_result"]["missing_fact_provenance"] = ["tax_period_start"]
    elif fault == "no-evidence":
        item["evidence_ids"] = []
    elif fault == "no-procedure":
        item["procedure"] = ""
    with pytest.raises(ValueError):
        require_assessed_tax_scope(selected, body)


def test_report_category_requires_tax_scope_without_leaking_it_to_uae():
    base = {
        "title": "SYNTHETIC tax draft",
        "category": "india-tax-audit",
        "blocks": [
            {
                "key": "note",
                "title": "Synthetic note",
                "kind": "narrative",
                "text": "Synthetic only",
            }
        ],
        "rationale": "Independently assessed synthetic tax-period scope",
    }
    with pytest.raises(ValidationError):
        ReportTemplate.model_validate(base)
    assert ReportTemplate.model_validate(
        {**base, "tax_audit_scope": scope().model_dump(mode="json")}
    ).tax_audit_scope
    with pytest.raises(ValidationError):
        ReportTemplate.model_validate(
            {**base, "category": "uae-ct", "tax_audit_scope": scope().model_dump(mode="json")}
        )
    assert ReportTemplate.model_validate({**base, "category": "uae-ct"}).tax_audit_scope is None


def test_legacy_unscoped_reports_are_not_current_but_their_bodies_are_preserved():
    from app.modules.regulatory.tax_forms import SCOPE_CONTRACT, has_tax_scope_contract

    body = {"category": "india-tax-audit", "title": "Retained old draft"}
    before = deepcopy(body)
    assert not has_tax_scope_contract(body, []) and body == before
    body.update(
        tax_form_scope_contract=SCOPE_CONTRACT, tax_audit_scope=scope().model_dump(mode="json")
    )
    assert not has_tax_scope_contract(body, [])
    assert has_tax_scope_contract(body, [{"type": "event", "id": CASE}])
    assert not has_tax_scope_contract(body, [{"type": "record", "id": CASE}])
    assert has_tax_scope_contract({"category": "uae-ct"}, [])


@pytest.mark.parametrize(
    "declared,retained,comparison,passes",
    [
        ("2025-04-01", "2025-04-01", "exact", True),
        ("2025-04-01", "2026-04-01", "exact", False),
        (True, True, "exact", True),
        (True, 1, "exact", False),
        ("26", 26, "exact", False),
        ("26", "26", "exact", True),
        ("3CA-3CD", "3CB-3CD", "exact", False),
        ("100", "100.00", "numeric", True),
        ("100", "100.00", "exact", False),
    ],
)
async def test_source_fact_comparison_preserves_dates_booleans_and_form_identifiers(
    monkeypatch, declared, retained, comparison, passes
):
    import uuid
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi import HTTPException

    from app.modules.intelligence import service as intelligence
    from app.modules.regulatory.schemas import FactSource
    from app.modules.regulatory.service import validate_fact_sources
    from tests.unit.test_regulatory_evaluation import fixture

    obj = SimpleNamespace(
        id=uuid.uuid4(),
        root_id=uuid.uuid4(),
        version=1,
        sha256="a" * 64,
        body={"review_status": "REVIEWED", "selected": retained},
    )
    monkeypatch.setattr(intelligence, "event", AsyncMock(return_value=obj))
    binding = {
        "selected": FactSource(
            kind="intelligence", id=obj.id, path=["selected"], comparison=comparison
        )
    }
    call = validate_fact_sources(
        None, None, SimpleNamespace(id=uuid.uuid4()), fixture(), {"selected": declared}, binding, []
    )
    if passes:
        assert await call == []
    else:
        with pytest.raises(HTTPException) as error:
            await call
        assert error.value.status_code == 422


@pytest.mark.parametrize(
    "start,end,expected",
    [
        ("2025-04-01", "2026-03-31", True),
        ("2025-01-01", "2026-12-31", True),
        ("2025-04-02", "2026-03-31", False),
        ("2025-04-01", "2026-03-30", False),
    ],
)
def test_tax_period_must_be_covered_by_engagement(start, end, expected):
    from datetime import date

    assert scope().covered_by(date.fromisoformat(start), date.fromisoformat(end)) is expected


def test_documented_adverse_clause_does_not_prevent_working_draft():
    selected = scope()
    body = assessed(selected)
    exception = deepcopy(body["items"][0])
    exception["state"] = "EXCEPTION_IDENTIFIED"
    exception["conclusion"] = "SYNTHETIC documented adverse finding requires report disclosure"
    body["items"].append(exception)
    require_assessed_tax_scope(selected, body)
    exception["evidence_ids"] = []
    with pytest.raises(ValueError, match="documented exceptions"):
        require_assessed_tax_scope(selected, body)
