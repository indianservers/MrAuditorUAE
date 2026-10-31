from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.regulatory.caro_index import LEAVES, manifest, scope_receipt
from app.modules.regulatory.schemas import ReportBlock, ReportTemplate
from app.modules.regulatory.workpaper_report_scope import require_mapping
from tests.unit.test_workpaper_report_scope import paper


def config(scope="standalone"):
    pack = manifest("india-caro-index:" + scope + "/1")
    return {
        "title": "SYNTHETIC CARO inventory",
        "category": "caro",
        "requirements_pack": pack["id"],
        "company_reporting_scope_id": str(uuid4()),
        "requirements": [{**r, "disposition": "REQUIRED"} for r in pack["requirements"]],
        "requirements_assessed": True,
        "requirements_basis": "SYNTHETIC every numbered matter explicitly assessed",
        "blocks": [
            {
                "key": "draft",
                "title": "SYNTHETIC draft",
                "kind": "narrative",
                "text": "SYNTHETIC no opinion qualification",
            }
        ],
        "rationale": "SYNTHETIC clause inventory workflow",
    }


def test_distinct_standalone_and_consolidated_inventories_include_both_reason_duties():
    assert len(LEAVES) == 48 and len({ref for ref, _ in LEAVES}) == 48
    for scope, count in (("standalone", 50), ("consolidated", 3)):
        pack = manifest("india-caro-index:" + scope + "/1")
        assert len(pack["requirements"]) == count
        assert {"caro.4.1", "caro.4.2"} <= {r["key"] for r in pack["requirements"]}
        assert not pack["statutory_completeness_qualified"]
        assert ReportTemplate.model_validate(config(scope)).company_reporting_scope_id is not None


@pytest.mark.parametrize("fault", ["scope", "omit", "no-source", "not-applicable"])
def test_inventory_cannot_omit_scope_or_required_matter(fault):
    data = config()
    if fault == "scope":
        data.pop("company_reporting_scope_id")
    elif fault == "omit":
        data["requirements"].pop()
    elif fault == "no-source":
        data["requirements"][0]["source_required"] = False
    else:
        data["requirements"][0]["disposition"] = "NOT_APPLICABLE"
    with pytest.raises(ValidationError):
        ReportTemplate.model_validate(data)


@pytest.mark.parametrize("wrong_period", [False, True])
def test_caro_workpaper_mapping_requires_same_period_and_explicit_item(wrong_period):
    key = "caro.3.i.a.A"
    body = paper(key)
    body["report_requirement_scope"].update(
        preset_id="india-caro-index:standalone/1",
        period_start="2025-04-01",
        period_end="2026-03-31",
    )
    block = ReportBlock(
        key="scope",
        title="Mapped clause",
        kind="working_paper_reference",
        source_kind="record",
        source_id=uuid4(),
        requirement_keys=[key],
    )
    period = SimpleNamespace(
        start_date=date(2025, 4, 2) if wrong_period else date(2025, 4, 1),
        end_date=date(2026, 3, 31),
    )
    if wrong_period:
        with pytest.raises(HTTPException):
            require_mapping(ReportTemplate.model_validate(config()), block, body, period=period)
    else:
        require_mapping(ReportTemplate.model_validate(config()), block, body, period=period)


@pytest.mark.parametrize("fault", ["exempt", "unreviewed", "wrong-period", "wrong-scope"])
async def test_missing_caro_duty_never_becomes_report_authority(monkeypatch, fault):
    from app.modules.country_workflows.india_company_scope import BINDING, CONTRACT
    from app.modules.intelligence import service

    row = {
        "period_start": "2025-04-01",
        "period_end": "2026-03-31",
        "statement_scope": "standalone",
        "caro_full_standalone_matters": True,
    }
    body = {
        "workflow": "india-company-reporting-scope",
        "contract": CONTRACT,
        "company_scope_document_binding": BINDING,
        "blocked": False,
        "review_status": "REVIEWED",
        "rows": [row],
    }
    if fault == "exempt":
        row["caro_full_standalone_matters"] = False
    elif fault == "unreviewed":
        body["review_status"] = "UNVERIFIED"
    elif fault == "wrong-period":
        row["period_end"] = "2026-03-30"
    else:
        row["statement_scope"] = "consolidated"
    monkeypatch.setattr(
        service,
        "event",
        AsyncMock(return_value=SimpleNamespace(kind="country-workflow", body=body)),
    )
    db = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(start_date=date(2025, 4, 1), end_date=date(2026, 3, 31))
        )
    )
    with pytest.raises(HTTPException):
        await scope_receipt(
            db,
            None,
            SimpleNamespace(id=uuid4(), period_id=uuid4()),
            ReportTemplate.model_validate(config()),
        )
