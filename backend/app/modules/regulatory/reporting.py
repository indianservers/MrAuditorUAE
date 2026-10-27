"""Composable reports using authorized immutable sources; no signing or filing adapter."""

import json

from fastapi import HTTPException

from app.db.models.platform import FinancialPeriod
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.access import engagement_permissions
from app.modules.intelligence import service as intelligence
from app.modules.jurisdictions.workspace import resolved
from app.modules.regulatory.report_requirements import (
    CONTRACT,
    coverage,
    implementation_hash,
    parse_template,
    require_ready,
)
from app.modules.regulatory.tax_forms import SCOPE_CONTRACT, require_assessed_tax_scope


async def tax_scope_receipt(db, ctx, eng, config):
    if config.tax_audit_scope is None:
        return []
    period = await db.get(FinancialPeriod, eng.period_id) if eng.period_id else None
    if period is None or not config.tax_audit_scope.covered_by(period.start_date, period.end_date):
        raise HTTPException(
            422, "The selected tax-audit period must be covered by the engagement financial period"
        )
    source = await intelligence.event(
        db, ctx, eng.id, config.tax_audit_scope.applicability_id, True
    )
    if source.kind != "statutory-checklist":
        raise HTTPException(409, "Select the reviewed India tax-audit applicability checklist")
    try:
        require_assessed_tax_scope(config.tax_audit_scope, source.body)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return [intelligence.event_receipt(source)]


def engines():
    from app.modules.ifrs.models import CalculationRun
    from app.modules.ifrs.service import current_dependencies
    from app.modules.tax.models import TaxRun
    from app.modules.tax.service import dependencies_current
    from app.modules.tp.models import TPRun
    from app.modules.tp.service import current as tp_current
    from app.modules.vat.models import VATRun
    from app.modules.vat.service import current as vat_current

    return {
        "ifrs": (CalculationRun, "ifrs.read", current_dependencies),
        "tax": (TaxRun, "tax.profile.read", dependencies_current),
        "tp": (TPRun, "tp.read", tp_current),
        "vat": (VATRun, "vat.read", vat_current),
    }


async def template(db, ctx, eng, data, request_id):
    binding, _ = await resolved(db, ctx, eng)
    if data.category.startswith("india-") or data.category in {"caro", "schedule-iii"}:
        if binding.country != "IN":
            raise HTTPException(
                422, "Indian report template requires the approved Indian engagement context"
            )
    if data.category.startswith("uae-") and binding.country != "AE":
        raise HTTPException(422, "UAE report template requires the approved UAE engagement context")
    dependencies = await tax_scope_receipt(db, ctx, eng, data)
    for block in data.blocks:
        if block.source_kind == "intelligence":
            source = await intelligence.event(db, ctx, eng.id, block.source_id, True)
            if source.kind in {"statutory-report", "report-template"}:
                raise HTTPException(
                    422,
                    "Choose underlying source results; nested report/template content is not a calculation source",
                )
            dependencies.append(intelligence.event_receipt(source))
        elif block.source_kind == "record":
            source = await audit.get_record(db, ctx, eng.id, block.source_id, lock=False)
            if source.status == "ARCHIVED":
                raise HTTPException(409, "Archived sources cannot be placed in a report")
            dependencies.append({"type": "record", "id": str(source.id), "version": source.version})
    prior = await intelligence.event(db, ctx, eng.id, data.prior_id) if data.prior_id else None
    if not prior and data.expected_version != 0:
        raise HTTPException(409, "New template must start with version zero")
    if prior and (prior.kind != "report-template" or prior.version != data.expected_version):
        raise HTTPException(409, "Template version conflict")
    return await intelligence.append(
        db,
        ctx,
        eng,
        "report-template",
        {
            **data.model_dump(mode="json", exclude={"prior_id", "expected_version"}),
            "review_status": "UNVERIFIED",
            "contributors": sorted(
                {str(ctx.user_id), *(prior.body.get("contributors", []) if prior else [])}
            ),
            "document_status": "DRAFT",
            "report_requirements_contract": CONTRACT,
            "report_requirements_implementation": implementation_hash(),
            "requirements_coverage": coverage(data),
            "scope": "Engagement-bound template; reuse requires an authorized copy with revalidated sources",
            **(
                {
                    "tax_form_scope_contract": SCOPE_CONTRACT,
                    "tax_form_selection_sources": data.tax_audit_scope.selection_sources(),
                }
                if data.tax_audit_scope
                else {}
            ),
        },
        dependencies,
        request_id,
        prior,
    )


async def generate(db, ctx, eng, data, request_id):
    stored = await intelligence.event(db, ctx, eng.id, data.template_id, True)
    if stored.kind != "report-template" or stored.body.get("review_status") != "REVIEWED":
        raise HTTPException(409, "Current independently reviewed template required")
    config = parse_template(stored.body)
    requirements_coverage = await require_ready(db, ctx, eng, config)
    scope_dependencies = await tax_scope_receipt(db, ctx, eng, config)
    blocks, dependencies = [], [intelligence.event_receipt(stored), *scope_dependencies]
    for index, block in enumerate(config.blocks, 1):
        source_body = None
        provenance = None
        if block.source_kind == "intelligence":
            source = await intelligence.event(db, ctx, eng.id, block.source_id, True)
            if source.body.get("review_status") != "REVIEWED":
                raise HTTPException(409, "Report input result is not independently reviewed")
            dependencies.append(intelligence.event_receipt(source))
            source_body = source.body
            provenance = {"id": str(source.id), "version": source.version, "sha256": source.sha256}
        elif block.source_kind == "record":
            source = await audit.get_record(db, ctx, eng.id, block.source_id, lock=False)
            if source.status not in {"APPROVED", "LOCKED", "RESOLVED", "CLOSED"} and not (
                source.kind == "findings" and source.status == "ACCEPTED_UNRESOLVED"
            ):
                raise HTTPException(409, "Report input audit record is not reviewed")
            from app.modules.lineage.working_papers import require_current

            await require_current(db, ctx, source)
            dependencies.append({"type": "record", "id": str(source.id), "version": source.version})
            source_body = source.body
            provenance = {"id": str(source.id), "version": source.version, "status": source.status}
            if block.calculation_id:
                model, permission, check = engines()[block.calculation_module]
                await engagement_permissions(db, ctx, eng.id, permission)
                calculated = await db.get(model, block.calculation_id)
                if (
                    not calculated
                    or calculated.engagement_id != eng.id
                    or source.body.get("run_id") != str(calculated.id)
                ):
                    raise HTTPException(
                        422, "The approved release record must reference this exact calculation"
                    )
                if not await check(db, ctx, eng.id, calculated):
                    raise HTTPException(409, "Calculation dependencies changed")
                source_body = calculated.results
                provenance.update(
                    calculation_id=str(calculated.id), calculation_sha256=calculated.sha256
                )
                dependencies.append(
                    {
                        "type": "calculation",
                        "module": block.calculation_module,
                        "id": str(calculated.id),
                        "sha256": calculated.sha256,
                    }
                )
        blocks.append(
            {
                "number": index,
                **block.model_dump(mode="json"),
                "data": source_body,
                "source_receipt": provenance,
                "narrative_origin": "USER_AUTHORED" if block.text else "SOURCE_ONLY",
            }
        )
        if len(json.dumps(blocks).encode()) > 20 * 1024 * 1024:
            raise HTTPException(
                422, "Resolved report source data exceeds 20 MiB; split the reporting package"
            )
    return await intelligence.append(
        db,
        ctx,
        eng,
        "statutory-report",
        {
            "title": config.title,
            "category": config.category,
            "requirements": [item.model_dump(mode="json") for item in config.requirements],
            "requirements_assessed": config.requirements_assessed,
            "requirements_basis": config.requirements_basis,
            "requirements_coverage": requirements_coverage,
            "report_requirements_contract": CONTRACT,
            "report_requirements_implementation": implementation_hash(),
            "blocks": blocks,
            "template_id": str(stored.id),
            "template_version": stored.version,
            "template_sha256": stored.sha256,
            "rationale": data.rationale,
            "document_status": "DRAFT — NOT SIGNED OR FILED",
            "review_status": "UNVERIFIED",
            "contributors": [str(ctx.user_id)],
            "missing_disclosures_fabricated": False,
            **(
                {
                    "tax_audit_scope": config.tax_audit_scope.model_dump(mode="json"),
                    "tax_form_regime": "2025-ACT"
                    if config.tax_audit_scope.form == "26"
                    else "1961-ACT",
                    "tax_form_content_qualified": False,
                    "tax_form_scope_contract": SCOPE_CONTRACT,
                    "tax_form_selection_sources": config.tax_audit_scope.selection_sources(),
                }
                if config.tax_audit_scope
                else {}
            ),
        },
        dependencies,
        request_id,
    )
