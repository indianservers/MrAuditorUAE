"""Protected context packets for assessed MSE facts; no semantic/registry attestation."""

import re
from uuid import UUID

from fastapi import HTTPException

CONTRACT = "retained-msme-context/1"
VERIFIED = "RETAINED_DOCUMENT_BYTES_VERIFIED"
UNRESOLVED = "NO_RESOLVED_FACTS_CLAIMED"


def needs_context(table_type, rows):
    if table_type == "msme-supplier-assessments":
        return any(r.get("eligibility") in {"ELIGIBLE", "INELIGIBLE"} for r in rows)
    if table_type == "msme-invoices":
        return any(
            (r.get("delivery_date") and r.get("acceptance_evidence_reference"))
            or r.get("written_objection_date")
            or r.get("objection_removed_date")
            or (r.get("terms_written") and r.get("agreed_due_date"))
            for r in rows
        )
    return False


def receipt_matches(context, dependencies):
    if not isinstance(context, dict):
        return False
    try:
        UUID(str(context.get("evidence_version_id")))
    except (ValueError, TypeError):
        return False
    if not re.fullmatch(r"[a-f0-9]{64}", str(context.get("sha256"))):
        return False
    return len(str(context.get("assessment", "")).strip()) >= 10 and any(
        isinstance(r, dict)
        and r.get("type") == "evidence"
        and r.get("id") == context.get("evidence_version_id")
        and r.get("sha256") == context.get("sha256")
        for r in dependencies
    )


def current_contract(body, dependencies):
    table = str(body.get("table_type") or "")
    if table.startswith("msme-"):
        if body.get("msme_evidence_contract") != CONTRACT:
            return False
        context = body.get("msme_evidence_context")
        return (
            receipt_matches(context, dependencies)
            if context
            else not needs_context(table, body.get("rows", []))
        )
    if body.get("workflow") == "india-msme-payment-timing":
        if body.get("msme_evidence_contract") != CONTRACT:
            return False
        contexts = body.get("retained_msme_contexts", [])
        if body.get("msme_document_binding") == VERIFIED:
            return bool(contexts) and all(receipt_matches(c, dependencies) for c in contexts)
        if body.get("msme_document_binding") == UNRESOLVED:
            return not contexts and all(
                not needs_context("msme-invoices", [r.get("retained_invoice_facts") or {}])
                and not needs_context(
                    "msme-supplier-assessments", [r.get("retained_supplier_assessment") or {}]
                )
                for r in body.get("rows", [])
            )
        return False
    return True


async def verify(db, ctx, eng, source, contributors):
    from app.modules.country_workflows.service import payroll_rule_documents

    context = source.get("msme_evidence_context")
    if not context:
        if needs_context(source["table_type"], source["rows"]):
            raise HTTPException(
                409, "Regenerate resolved MSE facts with a distinct retained context document"
            )
        return []
    if context["evidence_version_id"] == source.get("evidence_version_id") or context[
        "sha256"
    ] == source.get("evidence_sha256"):
        raise HTTPException(
            422, "An MSE source cannot corroborate itself or a copy of its own file"
        )
    return await payroll_rule_documents(
        db,
        ctx,
        eng,
        [
            {
                "source_evidence_version_id": context["evidence_version_id"],
                "source_sha256": context["sha256"],
            }
        ],
        label="MSE context",
        contributors=contributors,
    )


async def prepare(db, ctx, eng, data, original, rows, contributors):
    from app.modules.intelligence import service

    source = {
        "table_type": data.table_type,
        "rows": rows,
        "evidence_version_id": str(original.id),
        "evidence_sha256": original.sha256,
    }
    if data.msme_context_evidence_version_id is not None:
        document, _ = await service.evidence(
            db, ctx, eng, UUID(str(data.msme_context_evidence_version_id))
        )
        source["msme_evidence_context"] = {
            "evidence_version_id": str(document.id),
            "sha256": document.sha256,
            "record_id": str(document.record_id),
            "filename": document.filename,
            "assessment": data.msme_context_assessment.strip(),
        }
    receipts = await verify(db, ctx, eng, source, contributors)
    return source.get("msme_evidence_context"), receipts
