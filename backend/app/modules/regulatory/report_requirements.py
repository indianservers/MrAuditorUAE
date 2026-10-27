"""Declared mandatory-item coverage; no statutory completeness or legal qualification inferred."""

import hashlib
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import Field

from app.modules.jurisdictions.profiles import Strict
from app.modules.regulatory.report_packs import manifest

CONTRACT = "declared-report-requirements/2"


class ReportRequirement(Strict):
    key: str = Field(pattern=r"^[a-zA-Z0-9_.:-]{1,100}$")
    title: str = Field(min_length=3, max_length=300)
    disposition: Literal["REQUIRED", "NOT_APPLICABLE", "UNASSESSED"] = "UNASSESSED"
    source_required: bool = Field(default=True, strict=True)
    basis: str = Field(min_length=10, max_length=2000)


def implementation_hash():
    root = Path(__file__).parent
    digest = hashlib.sha256(CONTRACT.encode())
    for name in (
        "report_requirements.py",
        "reporting.py",
        "schemas.py",
        "report_packs.py",
        "form26_index.py",
    ):
        digest.update(name.encode() + b"\0" + hashlib.sha256((root / name).read_bytes()).digest())
    return digest.hexdigest()


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
        "requirements_pack": manifest(config.requirements_pack)
        if config.requirements_pack
        else None,
        "declared_scope_assessed": config.requirements_assessed,
        "scope_basis": config.requirements_basis,
        "items": rows,
        "complete": complete,
        "source_validation": "RECHECK_BEFORE_REVIEW_OR_GENERATION",
        "statutory_completeness_qualified": False,
    }


def preparers(source, *, record=False):
    """Inherit declared preparers, not the latest independent review event's creator."""
    contributors = {str(value) for value in source.body.get("contributors", []) if value}
    if record or not contributors:
        if source.created_by is not None:
            contributors.add(str(source.created_by))
    return contributors


async def record_preparers(db, ctx, source):
    from sqlalchemy import select

    from app.modules.audit_execution.models import AuditRevision

    # Select only distinct preparer identities, not potentially large paper bodies.
    authors = (
        await db.scalars(
            select(AuditRevision.snapshot["prepared_by"].astext)
            .where(AuditRevision.tenant_id == ctx.tenant_id, AuditRevision.record_id == source.id)
            .distinct()
        )
    ).all()
    result = preparers(source, record=True)
    result.update(str(author) for author in authors if author)
    if source.prepared_by is not None:
        result.add(str(source.prepared_by))
    return result


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
    from app.db.models.platform import FinancialPeriod
    from app.modules.audit_execution import service as audit
    from app.modules.intelligence import service as intelligence
    from app.modules.jurisdictions.workspace import resolved
    from app.modules.lineage.working_papers import require_current
    from app.modules.regulatory.report_packs import manifest, validate_source

    pack = manifest(config.requirements_pack) if config.requirements_pack else None
    if pack and (await resolved(db, ctx, eng))[0].country != pack["country"]:
        raise HTTPException(422, "Report preset is unavailable for this engagement country")
    vat_pack = pack and pack["kind"] == "vat201-comparison"
    period = await db.get(FinancialPeriod, eng.period_id) if vat_pack else None
    if (
        vat_pack
        and len({block.source_id for block in config.blocks if block.requirement_keys}) != 1
    ):
        raise HTTPException(409, "All VAT201 preset boxes must reference one reviewed comparison")

    result = coverage(config)
    if not result["complete"]:
        raise HTTPException(
            409,
            "Assess the declared report scope and resolve every required item's coverage before approval or generation",
        )
    for block in config.blocks:
        if block.source_kind == "intelligence":
            if pack and pack["kind"] == "form26-index" and block.requirement_keys:
                raise HTTPException(
                    409,
                    "Form 26 index items require current reviewed workpapers, not generic intelligence/checklist output",
                )
            source = await intelligence.event(db, ctx, eng.id, block.source_id, True)
            if source.body.get("review_status") != "REVIEWED":
                raise HTTPException(409, "Required report sources need current independent review")
            if vat_pack and block.requirement_keys:
                validate_source(pack, source.body, block.requirement_keys)
                from datetime import date

                if not period or any(
                    not period.start_date
                    <= date.fromisoformat(row["period_start"])
                    <= date.fromisoformat(row["period_end"])
                    <= period.end_date
                    for row in source.body["rows"]
                ):
                    raise HTTPException(
                        409,
                        "VAT201 report period must be covered by the engagement financial period",
                    )
        elif block.source_kind == "record":
            if vat_pack and block.requirement_keys:
                raise HTTPException(
                    409, "VAT201 preset coverage requires the reviewed comparison result"
                )
            source = await audit.get_record(db, ctx, eng.id, block.source_id, lock=False)
            if (
                pack
                and pack["kind"] == "form26-index"
                and block.requirement_keys
                and source.kind != "working-papers"
            ):
                raise HTTPException(
                    409, "Form 26 index coverage requires reviewed workpaper records"
                )
            allowed = {"APPROVED", "LOCKED", "RESOLVED", "CLOSED"}
            if source.kind == "findings":
                allowed.add("ACCEPTED_UNRESOLVED")
            if source.status not in allowed:
                raise HTTPException(409, "Required report source records need professional review")
            await require_current(db, ctx, source)
    return {**result, "source_validation": "CURRENT_REVIEWED_SOURCES_RECHECKED"}
