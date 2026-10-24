"""Business-question adapters call the same governed services as specialist UIs."""

import uuid
from typing import Literal

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import select

from app.modules.audit_execution import service as audit
from app.modules.audit_execution.models import AuditRecord
from app.modules.audit_execution.schemas import RecordInput, Strict
from app.modules.enterprise_ai.security import digest, scope, serial
from app.modules.jurisdictions.ae.use_cases import CASES, MANIFEST
from app.modules.jurisdictions.workspace import resolved


class Execute(Strict):
    action: Literal[
        "advanced-review",
        "calculate",
        "registration-exposure",
        "historical-vat-errors",
        "fx-review",
        "prepare-readiness-pack",
        "request-approved-export",
        "workflow",
        "draft-workpaper",
        "draft-finding",
        "draft-evidence-request",
        "draft-review-task",
        "draft-client-query",
        "propose-adjustment",
    ]
    idempotency_key: str = Field(min_length=8, max_length=100)
    record_id: uuid.UUID | None = None
    payload: dict = Field(default_factory=dict)


async def case_scope(db, ctx, eid, identifier, permission="ai.investigation.read"):
    eng = await scope(db, ctx, eid, permission)
    package, context = await resolved(db, ctx, eng)
    if package.country != "AE":
        raise HTTPException(422, "This use case belongs to the UAE jurisdiction package")
    if identifier == 48:
        from app.modules.audit_execution.access import engagement_permissions

        await engagement_permissions(db, ctx, eid, "audit.evidence.review")
    case = CASES.get(identifier)
    if case is None:
        raise HTTPException(404, "Unknown UAE business use case")
    return eng, case, context


async def inputs(db, ctx, eid, identifier, limit=20):
    eng, case, context = await case_scope(db, ctx, eid, identifier)
    package, _ = await resolved(db, ctx, eng)
    # Each row goes through its specialist getter; existence alone never grants access.
    candidates = (
        await db.scalars(
            select(AuditRecord)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.kind.in_(case.input_kinds),
                AuditRecord.status != "ARCHIVED",
            )
            .order_by(AuditRecord.updated_at.desc(), AuditRecord.id.desc())
            .limit(limit)
        )
    ).all()
    rows = []
    for candidate in candidates:
        try:
            obj = await audit.get_record(db, ctx, eid, candidate.id, lock=False)
        except HTTPException as exc:
            if exc.status_code in {403, 404}:
                continue
            raise
        rows.append(
            {
                "id": str(obj.id),
                "kind": obj.kind,
                "title": obj.title,
                "version": obj.version,
                "status": obj.status,
                "reference": obj.reference,
            }
        )
    return {
        "use_case": case.model_dump(),
        "items": rows,
        "context_version": context["version"],
        "context_receipt": {
            "case_catalogue_sha256": digest(MANIFEST),
            "type": "jurisdiction",
            "id": str(eid),
            "country": "AE",
            "version": context["version"],
            "sha256": package.package_sha256,
        },
        "missing_information": case.required_information,
        "checklist_meaning": "Required facts to verify in source records; collection does not establish their truth",
        "execution_mode": "deterministic_source_collection",
        "professional_conclusion": None,
        "module_url": module_url(case, eid),
    }


def module_url(case, eid):
    overrides = {
        1: f"/vat/{eid}/rules",
        20: f"/tp/{eid}/relationships",
        25: f"/engagements/{eid}/planning",
        26: f"/engagements/{eid}/materiality",
        27: "/audit/analytics",
        38: f"/engagements/{eid}/findings",
        45: f"/ifrs/{eid}/trial-balance",
    }
    if case.id in overrides:
        return overrides[case.id]
    if case.workflow:
        return f"/intelligence/{eid}/country-workflow"
    family = case.calculation.family if case.calculation else "audit"
    if family == "audit":
        return f"/engagements/{eid}/working-papers"
    if family == "dmtt":
        return "/pillar-two/scope"
    if family == "ifrs":
        kind = case.calculation.kind
        area = {
            "lease": "leases",
            "profile": "dashboard",
            "employee-benefits": "employee-benefits",
        }.get(kind, kind)
        return f"/ifrs/{eid}/{area}"
    if family == "vat" and case.calculation.kind == "einvoicing":
        return f"/vat/{eid}/einvoicing"
    return f"/{family}/{eid}/" + {
        "tax": "taxpayers",
        "vat": "invoices",
        "ifrs": "schedules",
        "tp": "loans",
        "dmtt": "scope",
        "audit": "working-papers",
    }.get(family, "working-papers")


async def execute(db, ctx, eid, identifier, data: Execute, request_id):
    eng, case, _ = await case_scope(db, ctx, eid, identifier, "ai.workflow.run")
    await audit.engagement(db, ctx, eid, "ai.workflow.run", True)
    if identifier == 48 and (
        data.action.startswith("draft-") or data.action == "propose-adjustment"
    ):
        raise HTTPException(
            409,
            "Restricted AML case-workpaper storage is required; generic drafts cannot copy this workstream into broader-access records",
        )
    from app.modules.enterprise_ai.service import locked
    from app.modules.intelligence import service as intelligence
    from app.modules.intelligence.models import IntelligenceEvent

    fingerprint = digest(data.model_dump(mode="json"))
    await locked(db, ctx, f"business:{ctx.user_id}:{data.idempotency_key}")
    previous = await db.scalar(
        select(IntelligenceEvent).where(
            IntelligenceEvent.tenant_id == ctx.tenant_id,
            IntelligenceEvent.engagement_id == eid,
            IntelligenceEvent.created_by == ctx.user_id,
            IntelligenceEvent.kind == "business-action",
            IntelligenceEvent.body["idempotency_key"].astext == data.idempotency_key,
        )
    )
    if previous:
        if (
            previous.body["request_sha256"] != fingerprint
            or previous.body["use_case_id"] != identifier
        ):
            raise HTTPException(409, "Idempotency key payload differs")
        await intelligence.event(db, ctx, eid, previous.id, True)
        return audit.serialize(previous)
    dependencies = []
    if data.action == "advanced-review":
        from app.modules.jurisdictions.ae.advanced import Schedule, calculate
        from app.modules.audit_execution.access import engagement_permissions
        from app.modules.enterprise_ai.security import source

        if identifier < 51 or not data.record_id or data.payload:
            raise HTTPException(422, "Select an approved case-specific schedule; runtime input overrides are forbidden")
        proof = await source(db, ctx, eid, data.record_id)
        if proof.kind != "working-papers" or not proof.body.get("advanced_input"):
            raise HTTPException(422, "Approved structured schedule workpaper required")
        schedule = Schedule.model_validate(proof.body["advanced_input"])
        if schedule.use_case_id != identifier:
            raise HTTPException(422, "Schedule belongs to a different use case")
        for engine, permission in {"E04":"vat.calculate", "E05":"tax.computation.prepare", "E07":"tp.calculate", "E08":"dmtt.calculate", "E09":"ifrs.calculation.execute"}.items():
            if engine in case.engines:
                await engagement_permissions(db, ctx, eid, permission)
        for source_id in {str(proof.id), str(schedule.policy.source_id), *(r["evidence_id"] for r in schedule.rows)}:
            evidence = await source(db, ctx, eid, uuid.UUID(source_id))
            dependencies.append({"type":"record", "id":str(evidence.id), "version":evidence.version})
        output = {"engine":"uae-advanced-schedules", "results":calculate(schedule),
                  "entity_id":str(eng.entity_id), "period_id":str(eng.period_id) if eng.period_id else None,
                  "input_record_id":str(proof.id), "input_version":proof.version,
                  "preparer_id":str(ctx.user_id), "input_assurance":"Independently approved supplied schedule; automatic source extraction/tie-out is not asserted"}
    elif data.action == "workflow":
        from app.modules.intelligence.jobs import submit
        from app.modules.intelligence.schemas import JobInput

        if not case.workflow:
            raise HTTPException(422, "This case has no shared workflow adapter")
        # The existing job schema validates each role, source ID, currency and population.
        job = await submit(
            db,
            ctx,
            eid,
            JobInput(
                operation="country-workflow", payload={**data.payload, "workflow": case.workflow}
            ),
            data.idempotency_key,
            request_id,
        )
        return {
            "job_id": str(job.id),
            "status": job.status,
            "execution_mode": "queued_deterministic_engine",
        }
    if data.action == "historical-vat-errors":
        if identifier != 8 or not data.record_id:
            raise HTTPException(
                422, "Select historical VAT errors and approved original/corrected-period evidence"
            )
        from app.modules.audit_execution.access import engagement_permissions
        from app.modules.jurisdictions.ae.vat_errors import ErrorSchedule
        from app.modules.jurisdictions.ae.vat_errors import calculate as calculate_errors

        await engagement_permissions(db, ctx, eid, "vat.calculate")
        proof = await audit.get_record(db, ctx, eid, data.record_id, lock=False)
        if proof.kind not in {"vat-return", "evidence", "working-papers"}:
            raise HTTPException(
                422, "Choose an original filing/corrected-data evidence pack or VAT return record"
            )
        if proof.status not in {"APPROVED", "LOCKED"}:
            raise HTTPException(
                409, "Approved historical filing and corrected-data evidence required"
            )
        schedule = ErrorSchedule.model_validate(data.payload)
        output = {"engine": "vat-error-schedule", "results": calculate_errors(schedule)}
        dependencies.append({"type": "record", "id": str(proof.id), "version": proof.version})
    elif data.action == "prepare-readiness-pack":
        from app.modules.tax.connected import ConnectedInput, assess

        await audit.engagement(db, ctx, eid, "tax.computation.prepare", True)
        pack = await assess(db, ctx, eng, ConnectedInput.model_validate(data.payload), request_id)
        dependencies.append(intelligence.event_receipt(pack))
        output = {
            "id": str(pack.id),
            "kind": pack.kind,
            "completeness": pack.body["completeness"],
            "issues": pack.body["issues"],
            "filing_status": "NOT_SUBMITTED",
            "authority_assessment": "NOT_ESTABLISHED",
        }
    elif data.action == "request-approved-export":
        if not data.record_id:
            raise HTTPException(422, "Select an independently reviewed report or schedule")
        from app.modules.audit_execution.access import engagement_permissions

        await engagement_permissions(db, ctx, eid, "audit.export")
        export = await intelligence.event(db, ctx, eid, data.record_id, True)
        if export.body.get("review_status") != "REVIEWED":
            raise HTTPException(
                409,
                "Only independently reviewed current results may use this approved-export action",
            )
        dependencies.append(intelligence.event_receipt(export))
        output = {
            "id": str(export.id),
            "authorized_download_endpoint": f"/intelligence/engagements/{eid}/events/{export.id}/export",
            "meaning": "Download authorization only; the export endpoint rechecks permissions and produces the artifact",
            "accepted_filing": False,
        }
    elif data.action == "fx-review":
        if identifier != 45 or not data.record_id:
            raise HTTPException(422, "Select FX review and approved classification/rate evidence")
        from app.modules.audit_execution.access import engagement_permissions
        from app.modules.ifrs.fx import MonetaryBalance, closing_revaluation

        await engagement_permissions(db, ctx, eid, "ifrs.calculation.execute")
        evidence = await audit.get_record(db, ctx, eid, data.record_id, lock=False)
        if evidence.status not in {"APPROVED", "LOCKED"}:
            raise HTTPException(
                409, "Approved rate and monetary-item classification evidence required"
            )
        if set(data.payload) != {"balances", "rounding_precision"}:
            raise HTTPException(422, "Provide balances and rounding_precision only")
        balances = [MonetaryBalance.model_validate(row) for row in data.payload["balances"]]
        output = {
            "engine": "ifrs-fx",
            "results": closing_revaluation(balances, data.payload["rounding_precision"]),
            "input_assurance": "Supplied balances/rates linked to reviewed evidence; automated ledger tie-out is not asserted",
        }
        dependencies.append({"type": "record", "id": str(evidence.id), "version": evidence.version})
    elif data.action == "registration-exposure":
        if identifier != 1 or not data.record_id:
            raise HTTPException(422, "Select VAT registration and an approved effective rule")
        from app.modules.audit_execution.access import engagement_permissions
        from app.modules.jurisdictions.ae.registration import Exposure
        from app.modules.jurisdictions.ae.registration import calculate as calculate_registration
        from app.modules.vat import service as vat
        from app.modules.vat.schemas import Rule

        await engagement_permissions(db, ctx, eid, "vat.calculate")
        rule = await vat.record(db, ctx, eid, data.record_id, "rule", True)
        body = Rule.model_validate(vat.clean(rule.body))
        population = Exposure.model_validate(data.payload)
        vat.applicable(body, population.as_of)
        if body.category != "registration" or body.registration_parameters is None:
            raise HTTPException(
                409, "Approved registration parameters and source adoption are required"
            )
        # Each amount is tied to an authorized journal line or approved forecast evidence record.
        from app.modules.enterprise_ai.tools import journal_source

        seen_journals = set()
        for row in population.historical:
            line = await journal_source(db, ctx, eid, uuid.UUID(row.id))
            if line.functional_currency != "AED":
                raise HTTPException(
                    422,
                    "Registration exposure requires reviewed AED source values; other functional currencies need an approved conversion workstream",
                )
            if line.journal_id in seen_journals:
                raise HTTPException(
                    422,
                    "Select one reviewed net source line per journal to prevent debit/credit or tax-line double counting",
                )
            seen_journals.add(line.journal_id)
            if (
                line.posting_date != row.date
                or line.base_debit + line.base_credit != row.amount_aed
            ):
                raise HTTPException(422, "Registration amount/date differs from source ledger line")
            dependencies.append((await intelligence.snapshot(db, ctx, eng, line.snapshot_id))[1])
        for row in population.forecast:
            forecast = await audit.get_record(db, ctx, eid, uuid.UUID(row.id), lock=False)
            if forecast.status not in {"APPROVED", "LOCKED"}:
                raise HTTPException(409, "Approved forecast evidence required")
            dependencies.append(
                {"type": "record", "id": str(forecast.id), "version": forecast.version}
            )
        dependencies.append({"type": "record", "id": str(rule.id), "version": rule.version})
        output = {
            "engine": "vat-registration",
            "results": calculate_registration(population, body.registration_parameters),
            "rule_id": str(rule.id),
            "rule_version": rule.version,
        }
    elif data.action == "calculate":
        if not case.calculation or not data.record_id:
            raise HTTPException(422, "Select a supported case and its approved input record")
        record = await audit.get_record(db, ctx, eid, data.record_id, lock=False)
        expected = case.calculation.family + "-" + case.calculation.kind
        if record.kind != expected:
            raise HTTPException(422, f"Input must be an approved {expected} record")
        if record.status not in {"APPROVED", "LOCKED"}:
            raise HTTPException(409, "Independent input approval is required before calculation")
        family = case.calculation.family
        from app.modules.dmtt import service as dmtt
        from app.modules.ifrs import service as ifrs
        from app.modules.tax import service as tax
        from app.modules.tp import service as tp
        from app.modules.vat import service as vat

        handlers = {
            ("tax", "compute"): tax.compute,
            ("tax", "calculate"): tax.calculate_record,
            ("vat", "compute"): vat.compute,
            ("vat", "invoice"): vat.invoice_result,
            ("vat", "assessment"): vat.assess_record,
            ("ifrs", "calculate"): ifrs.calculate_record,
            ("ifrs", "financials"): ifrs.financials,
            ("ifrs", "consolidate"): ifrs.consolidate,
            ("tp", "calculate"): tp.calculate,
            ("dmtt", "compute"): dmtt.computation,
        }
        result = await handlers[(family, case.calculation.operation)](db, ctx, eid, record.id)
        if case.calculation.operation == "invoice":
            obj, _, value = result
            output = {
                "id": str(obj.id),
                "engine": "vat",
                "kind": "invoice-validation",
                "results": value,
                "review_status": "UNREVIEWED",
                "source_record_id": str(obj.id),
            }
        dependencies.append({"type": "record", "id": str(record.id), "version": record.version})
        if case.calculation.operation != "invoice":
            result_id = str(result.id) if hasattr(result, "id") else str(result.get("id", ""))
            if family != "dmtt" and result_id:
                getter = {"ifrs": ifrs.run, "tax": tax.run, "vat": vat.run, "tp": tp.get_run}[
                    family
                ]
                retained = await getter(db, ctx, eid, uuid.UUID(result_id))
                dependencies.append(
                    {
                        "type": "calculation",
                        "module": family,
                        "id": result_id,
                        "sha256": retained.sha256,
                    }
                )
            elif family == "dmtt":
                dependencies.append({"type": "dmtt", "id": result_id, "sha256": result.sha256})
            output = {
                "id": result_id,
                "engine": family,
                "kind": case.calculation.kind,
                "review_status": "UNREVIEWED",
                "source_record_id": str(record.id),
                "detail": module_url(case, eid),
                "publication": "NOT_FILED_NOT_POSTED",
            }
            values = result.body.get("results", {}) if family == "dmtt" else retained.results
            import json

            preview = serial(values)
            output["calculation_breakdown"] = (
                preview
                if len(json.dumps(preview)) <= 24000
                else {
                    "limitation": "Detailed schedule exceeds preview limit; open the retained run in the specialist module",
                    "available_sections": list(preview),
                }
            )
    else:
        # Only explicitly selected reversible draft types. Normal record validation and
        # reviewer separation remain authoritative; no arbitrary URL or function dispatch.
        kinds = {
            "draft-finding": "findings",
            "draft-workpaper": "working-papers",
            "draft-evidence-request": "requests",
            "draft-review-task": "review-notes",
            "draft-client-query": "requests",
        }
        kind = kinds.get(data.action)
        if data.action == "propose-adjustment":
            family = case.calculation.family if case.calculation else "ifrs"
            kind = (family if family in {"tax", "vat", "ifrs"} else "ifrs") + "-adjustment"
        if kind is None:
            raise HTTPException(422, "Unsupported action")
        draft = RecordInput.model_validate(data.payload)
        if kind == "working-papers":
            draft.body["inherit_source_permissions"] = True
            for reference in draft.body.get("sources", []):
                if reference["kind"] == "intelligence":
                    src = await intelligence.event(
                        db, ctx, eid, uuid.UUID(str(reference["id"])), True
                    )
                    dependencies.append(intelligence.event_receipt(src))
                elif reference["kind"] in {"record", "finding"}:
                    src = await audit.get_record(
                        db, ctx, eid, uuid.UUID(str(reference["id"])), lock=False
                    )
                    dependencies.append(
                        {"type": "record", "id": str(src.id), "version": src.version}
                    )
        if data.action == "draft-finding":
            if (identifier != 38 and identifier < 51) or not draft.body.get("sources"):
                raise HTTPException(422, "Finding workflow requires reviewed source exceptions")
            for field in ("condition", "criteria", "cause", "effect", "recommendation"):
                if not str(draft.body.get(field, "")).strip():
                    raise HTTPException(
                        422, f"Finding needs {field}; record unknown facts explicitly"
                    )
            for reference in draft.body["sources"]:
                if reference["kind"] == "intelligence":
                    source = await intelligence.event(
                        db, ctx, eid, uuid.UUID(reference["id"]), True
                    )
                    if source.body.get("review_status") != "REVIEWED":
                        raise HTTPException(409, "Independently reviewed source exception required")
                    dependencies.append(intelligence.event_receipt(source))
                elif reference["kind"] == "record":
                    source = await audit.get_record(
                        db, ctx, eid, uuid.UUID(reference["id"]), lock=False
                    )
                    if source.status not in {"APPROVED", "LOCKED"}:
                        raise HTTPException(409, "Approved source exception required")
                    dependencies.append(
                        {"type": "record", "id": str(source.id), "version": source.version}
                    )
                else:
                    raise HTTPException(
                        422, "Findings must cite reviewed records or reviewed engine exceptions"
                    )
        # Uploaded narrative cannot turn a draft into an approved journal or a sent message.
        result = await audit.create(db, ctx, eid, kind, draft, request_id)
        output = {
            "id": result["id"],
            "kind": kind,
            "status": result["status"],
            "sent": False,
            "posted": False,
            "filing_submitted": False,
        }
    obj = await intelligence.append(
        db,
        ctx,
        eng,
        "business-action",
        {
            "use_case_id": identifier,
            "action": data.action,
            "idempotency_key": data.idempotency_key,
            "request_sha256": fingerprint,
            "case_catalogue_sha256": digest(MANIFEST),
            "output": serial(output),
            "execution_mode": "governed_draft_creation"
            if data.action.startswith("draft-") or data.action == "propose-adjustment"
            else "deterministic_engine",
            "review_status": "UNVERIFIED",
            "professional_conclusion": None,
        },
        dependencies,
        request_id,
    )
    return audit.serialize(obj)
