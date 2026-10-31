from copy import deepcopy

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.country_workflows.india_company_scope import BINDING, CONTRACT
from app.modules.regulatory.company_scope_pack import DECISIONS
from app.modules.regulatory.report_packs import manifest, validate_source
from app.modules.regulatory.schemas import ReportTemplate


def pack(scope="standalone"):
    return manifest("india-company-scope:" + scope + "/1")


def body():
    return {
        "workflow": "india-company-reporting-scope",
        "contract": CONTRACT,
        "company_scope_document_binding": BINDING,
        "blocked": False,
        "exception_count": 0,
        "rows": [
            {
                "statement_scope": "standalone",
                "state": "SUPPORTED",
                **{key: False for key in DECISIONS},
            }
        ],
    }


def config():
    preset = pack()
    return {
        "title": "SYNTHETIC company scope summary",
        "category": "india-statutory",
        "requirements_pack": preset["id"],
        "requirements": [{**r, "disposition": "REQUIRED"} for r in preset["requirements"]],
        "requirements_assessed": True,
        "requirements_basis": "SYNTHETIC all explicit decisions require current reviewed support",
        "blocks": [
            {
                "key": "scope",
                "title": "Company scope",
                "kind": "regulatory_checklist",
                "source_kind": "intelligence",
                "source_id": "00000000-0000-4000-8000-000000000001",
                "requirement_keys": [r["key"] for r in preset["requirements"]],
            }
        ],
        "rationale": "SYNTHETIC retained applicability summary only",
    }


def test_all_decisions_including_false_require_retained_source():
    preset = pack()
    assert len(preset["requirements"]) == 6
    assert not preset["statutory_completeness_qualified"]
    validate_source(preset, body(), [r["key"] for r in preset["requirements"]])
    assert ReportTemplate.model_validate(config()).requirements_pack == preset["id"]


@pytest.mark.parametrize(
    "failure",
    [
        "workflow",
        "contract",
        "binding",
        "blocked",
        "pending",
        "integer",
        "scope",
        "multiple",
        "state",
    ],
)
def test_generic_or_unresolved_results_cannot_cover_scope_decisions(failure):
    source = deepcopy(body())
    if failure == "workflow":
        source["workflow"] = "generic-checklist"
    elif failure == "contract":
        source["contract"] = "old"
    elif failure == "binding":
        source.pop("company_scope_document_binding")
    elif failure == "blocked":
        source["blocked"] = True
    elif failure == "pending":
        source["rows"][0]["small_company"] = None
    elif failure == "integer":
        source["rows"][0]["small_company"] = 0
    elif failure == "scope":
        source["rows"][0]["statement_scope"] = "consolidated"
    elif failure == "multiple":
        source["rows"].append(deepcopy(source["rows"][0]))
    else:
        source["rows"][0]["state"] = "EXCEPTION"
    with pytest.raises(HTTPException):
        validate_source(pack(), source, [r["key"] for r in pack()["requirements"]])


@pytest.mark.parametrize("failure", ["omit", "not-applicable", "narrative", "category"])
def test_scope_preset_cannot_weaken_required_decision_coverage(failure):
    data = config()
    if failure == "omit":
        data["requirements"].pop()
    elif failure == "not-applicable":
        data["requirements"][0]["disposition"] = "NOT_APPLICABLE"
    elif failure == "narrative":
        data["requirements"][0]["source_required"] = False
    else:
        data["category"] = "uae-ifrs"
    with pytest.raises(ValidationError):
        ReportTemplate.model_validate(data)
