"""Declared mandatory-item coverage; no statutory completeness or legal qualification inferred."""

import hashlib
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import Field

from app.modules.jurisdictions.profiles import Strict

CONTRACT = "declared-report-requirements/1"


class ReportRequirement(Strict):
    key: str = Field(pattern=r"^[a-zA-Z0-9_.:-]{1,100}$")
    title: str = Field(min_length=3, max_length=300)
    disposition: Literal["REQUIRED", "NOT_APPLICABLE", "UNASSESSED"] = "UNASSESSED"
    source_required: bool = Field(default=True, strict=True)
    basis: str = Field(min_length=10, max_length=2000)


def implementation_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def coverage(config):
    rows = []
    for requirement in config.requirements:
        blocks = [block for block in config.blocks if requirement.key in block.requirement_keys]
        sourced = [block for block in blocks if block.source_kind and block.source_id]
        covered = (
            bool(sourced)
            if requirement.source_required or requirement.disposition == "NOT_APPLICABLE"
            else any(block.text and len(block.text.strip()) >= 10 for block in blocks)
            or bool(sourced)
        )
        rows.append(
            {
                "key": requirement.key,
                "title": requirement.title,
                "disposition": requirement.disposition,
                "source_required": requirement.source_required
                or requirement.disposition == "NOT_APPLICABLE",
                "block_keys": [block.key for block in blocks],
                "status": "UNASSESSED"
                if requirement.disposition == "UNASSESSED"
                else "COVERED"
                if covered
                else "MISSING_COVERAGE",
            }
        )
    complete = (
        config.requirements_assessed
        and bool(rows)
        and len(config.requirements_basis.strip()) >= 10
        and all(row["status"] == "COVERED" for row in rows)
    )
    return {
        "contract": CONTRACT,
        "declared_scope_assessed": config.requirements_assessed,
        "scope_basis": config.requirements_basis,
        "items": rows,
        "complete": complete,
        "source_validation": "RECHECK_BEFORE_REVIEW_OR_GENERATION",
        "statutory_completeness_qualified": False,
    }


def current_contract(body):
    return (
        body.get("report_requirements_contract") == CONTRACT
        and body.get("report_requirements_implementation") == implementation_hash()
    )


def parse_template(body):
    from pydantic import ValidationError

    from app.modules.regulatory.schemas import ReportTemplate

    try:
        return ReportTemplate.model_validate(
            {key: value for key, value in body.items() if key in ReportTemplate.model_fields}
        )
    except ValidationError:
        raise HTTPException(
            409, "Amend the template and independently review its report requirements"
        ) from None


async def require_ready(db, ctx, eng, config):
    from app.modules.audit_execution import service as audit
    from app.modules.intelligence import service as intelligence
    from app.modules.lineage.working_papers import require_current

    result = coverage(config)
    if not result["complete"]:
        raise HTTPException(
            409,
            "Assess the declared report scope and resolve every required item's coverage before approval or generation",
        )
    for block in config.blocks:
        if block.source_kind == "intelligence":
            source = await intelligence.event(db, ctx, eng.id, block.source_id, True)
            if source.body.get("review_status") != "REVIEWED":
                raise HTTPException(409, "Required report sources need current independent review")
        elif block.source_kind == "record":
            source = await audit.get_record(db, ctx, eng.id, block.source_id, lock=False)
            allowed = {"APPROVED", "LOCKED", "RESOLVED", "CLOSED"}
            if source.kind == "findings":
                allowed.add("ACCEPTED_UNRESOLVED")
            if source.status not in allowed:
                raise HTTPException(409, "Required report source records need professional review")
            await require_current(db, ctx, source)
    return {**result, "source_validation": "CURRENT_REVIEWED_SOURCES_RECHECKED"}
