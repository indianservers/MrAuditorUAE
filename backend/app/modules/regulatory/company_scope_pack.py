"""Reviewed India applicability summary, not a complete audit report or opinion."""

from fastapi import HTTPException

from app.modules.country_workflows.india_company_scope import BINDING, CONTRACT
from app.modules.jurisdictions.packages import fingerprint

PREFIX = "india-company-scope:"
DECISIONS = {
    "small_company": "Small-company classification",
    "companies_act_section139_audit": "Companies Act section 139 audit duty",
    "caro2020_applies": "CARO 2020 applicability",
    "caro_full_standalone_matters": "CARO standalone matters",
    "caro_consolidated_paragraph3_xxi": "CARO consolidated paragraph 3(xxi)",
    "section143_3_i_ifc_reporting": "Section 143(3)(i) IFC reporting duty",
}


def manifest(identifier):
    if identifier not in {PREFIX + scope + "/1" for scope in ("standalone", "consolidated")}:
        raise ValueError("Unknown India company-scope summary preset")
    scope = identifier[len(PREFIX) : -2]
    body = {
        "id": identifier,
        "country": "IN",
        "category": "india-statutory",
        "kind": "india-company-scope-summary",
        "statement_scope": scope,
        "title": "India company reporting applicability summary — " + scope,
        "source_url": "https://github.com/indianservers/MrAuditorUAE/blob/main/docs/country-workflows/india-company-reporting-scope.txt",
        "source_version": "india-company-reporting-scope/1 operational contract; eight independently retained source roles, not a statutory text",
        "allow_not_applicable": False,
        "not_applicable_keys": [],
        "requirements": [
            {
                "key": "company.scope." + key,
                "title": title,
                "disposition": "UNASSESSED",
                "source_required": True,
                "basis": "Retain the explicit true or false decision from one current independently reviewed India company-scope workpaper",
            }
            for key, title in DECISIONS.items()
        ],
        "statutory_completeness_qualified": False,
        "limitations": [
            "Applicability summary only; this preset is not a complete statutory audit report, CARO clause report or audit opinion",
            "All six decisions require one current independently reviewed scope workpaper for the exact engagement period and statement scope",
            "A false duty still requires its retained decision; narrative and not-applicable overrides cannot replace the assessed source",
            "Original-byte integrity and workflow review do not authenticate the complete legal chain or authorize statutory issuance",
        ],
    }
    return {**body, "sha256": fingerprint(body)}


def validate_source(pack, body, requirement_keys):
    rows = body.get("rows", [])
    if (
        body.get("workflow") != "india-company-reporting-scope"
        or body.get("contract") != CONTRACT
        or body.get("company_scope_document_binding") != BINDING
        or body.get("blocked") is not False
        or body.get("exception_count") != 0
        or len(rows) != 1
        or rows[0].get("statement_scope") != pack["statement_scope"]
        or rows[0].get("state") != "SUPPORTED"
    ):
        raise HTTPException(
            409,
            "Select the current resolved India company-scope workpaper for this exact statement scope",
        )
    if any(type(rows[0].get(key)) is not bool for key in DECISIONS):
        raise HTTPException(
            409,
            "All company reporting decisions must be explicitly assessed; missing is not exempt",
        )
    if not set(requirement_keys) <= {"company.scope." + key for key in DECISIONS}:
        raise HTTPException(409, "Company-scope summary contains an unknown requirement")
