import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal, localcontext
from typing import Any

from fastapi import HTTPException
from sqlalchemy import any_, bindparam, func, select
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.db.models.platform import FinancialPeriod
from app.modules.accounting.models import Account, ImportBatch, JournalLine
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.models import AuditRecord, EvidenceVersion
from app.modules.audit_execution.schemas import Source
from app.modules.ifrs.calculations import serial
from app.modules.vat import calculations as calc
from app.modules.vat import schemas as s
from app.modules.vat.catalogue import BOXES, SOURCES
from app.modules.vat.models import VATRun

D = Decimal


def journal_ids(values):
    # One PostgreSQL UUID-array bind avoids asyncpg's 32,767 scalar-parameter ceiling.
    return JournalLine.id == any_(
        bindparam("vat_journal_ids", list(values), type_=ARRAY(UUID(as_uuid=True)))
    )


APPROVED = {"APPROVED", "LOCKED"}


def clean(body):
    return {k: v for k, v in body.items() if not k.startswith("review_")}


def dep(obj):
    return {"id": str(obj.id), "version": obj.version, "status": obj.status}


async def record(db, ctx, eid, rid, kind=None, approved=False):
    obj = await audit.get_record(db, ctx, eid, rid, "vat.read")
    if not obj.kind.startswith("vat-") or kind and obj.kind != "vat-" + kind:
        raise HTTPException(422, "Unexpected VAT record kind")
    if approved and obj.status not in APPROVED:
        raise HTTPException(409, "Independently approved VAT source required")
    if approved:
        from app.modules.lineage.working_papers import require_context_current

        await require_context_current(db, ctx, obj)
    return obj


async def evidence(db, ctx, eid, rid):
    obj = await audit.get_record(db, ctx, eid, rid, "vat.read")
    if obj.status not in APPROVED:
        raise HTTPException(409, "Reviewed VAT evidence required")
    if obj.kind == "evidence":
        latest = await db.scalar(
            select(EvidenceVersion)
            .where(EvidenceVersion.tenant_id == ctx.tenant_id, EvidenceVersion.record_id == rid)
            .order_by(EvidenceVersion.number.desc())
            .limit(1)
        )
        if not latest or latest.scan_status != "CLEAN":
            raise HTTPException(409, "Clean scanned VAT evidence required")
    return obj


def evidence_ids(body):
    result = []
    for key, value in body.items():
        if key.endswith("evidence_id") and value:
            result.append(uuid.UUID(str(value)))
        elif key.endswith("evidence_ids") or key == "evidence_record_ids":
            result.extend(uuid.UUID(str(x)) for x in value)
    return set(result)


async def rules(db, ctx, eid, profile):
    result = {}
    for category, rid in profile.rules.items():
        obj = await record(db, ctx, eid, rid, "rule", True)
        body = s.Rule.model_validate(clean(obj.body))
        if category != body.category or not body.active or body.known_from > profile.legal_as_of:
            raise HTTPException(409, "Selected VAT rule category/version/as-of is not applicable")
        result[category] = (obj, body)
    return result


def applicable(rule, when):
    if rule.effective_from > when or rule.effective_to and rule.effective_to < when:
        raise HTTPException(409, "VAT rule not applicable on the tax point")


async def profile_inputs(db, ctx, eid, pid):
    obj = await record(db, ctx, eid, pid, "profile", True)
    profile = s.Profile.model_validate(clean(obj.body))
    if profile.registration_status != "REGISTERED" or profile.accounting_basis != "accrual":
        raise HTTPException(
            409, "Registered accrual profile required; other basis needs specialist methodology"
        )
    return obj, profile, await rules(db, ctx, eid, profile)


async def validate_body(db, ctx, eng, kind, data, record_id=None):
    kind = kind.removeprefix("vat-")
    if kind == "rule":
        source = SOURCES.get(data.source_id)
        if not source or data.article and data.article not in source["articles"]:
            raise HTTPException(422, "Unverified VAT source/article")
        if (
            data.effective_from < date.fromisoformat(source["earliest"])
            or data.effective_to
            and data.effective_to < data.effective_from
        ):
            raise HTTPException(422, "Rule effective dates contradict registered commencement")
        if data.known_from < date.fromisoformat(source["earliest"]) and data.source_id not in {
            "VAT-LAW",
            "VAT-ER",
            "VAT-RETURN-GUIDE",
        }:
            raise HTTPException(422, "Legal knowledge precedes verified source")
        duplicate = await db.scalar(
            select(AuditRecord.id).where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eng.id,
                AuditRecord.kind == "vat-rule",
                AuditRecord.id != (record_id or uuid.UUID(int=0)),
                AuditRecord.body["rule_key"].astext == data.rule_key,
                AuditRecord.body["rule_version"].astext == str(data.rule_version),
            )
        )
        if duplicate:
            raise HTTPException(409, "Rule version already exists")
    if kind == "profile":
        period = await db.get(FinancialPeriod, eng.period_id)
        if not period.start_date <= data.period_start <= data.period_end <= period.end_date:
            raise HTTPException(422, "VAT period outside financial engagement period")
        if set(data.output_control_codes).intersection(data.input_control_codes):
            raise HTTPException(422, "Input/output control codes must be distinct")
        if data.vat_group_reference and not data.vat_group_approval_evidence_id:
            raise HTTPException(
                422, "VAT group approval evidence required; Corporate Tax grouping is insufficient"
            )
        if not {"output", "input", "invoice", "return"} <= data.rules.keys():
            raise HTTPException(422, "Approved output/input/invoice/return rule versions required")
        await rules(db, ctx, eng.id, data)
    if hasattr(data, "profile_id"):
        _, p, selected = await profile_inputs(db, ctx, eng.id, data.profile_id)
        if hasattr(data, "rule_id") and data.rule_id not in p.rules.values():
            raise HTTPException(422, "Assessment must reference a selected approved profile rule")
        if kind == "invoice":
            if (
                not p.registered_from <= data.tax_point
                or not p.period_start <= data.tax_point <= p.period_end
            ):
                raise HTTPException(422, "Invoice tax point outside registered VAT period")
            if (
                data.invoice_rule_id != p.rules["invoice"]
                or data.rule_id != p.rules["output" if data.direction == "sale" else "input"]
            ):
                raise HTTPException(422, "Invoice does not use selected treatment/invoice rule")
            for key in ["invoice", "output" if data.direction == "sale" else "input"]:
                applicable(selected[key][1], data.tax_point)
            if (
                data.direction == "purchase"
                and data.tax_point >= date(2026, 10, 1)
                and data.recovery_treatment != "blocked"
            ):
                integrity = selected.get("integrity")
                if not integrity or integrity[1].source_id != "FTA13-2026":
                    raise HTTPException(422, "Recovery requires approved FTA13 integrity rule")
                applicable(integrity[1], data.tax_point)
            if (
                data.employee_expense
                and data.tax_point >= date(2026, 10, 1)
                and data.recovery_treatment != "blocked"
            ):
                if (
                    not data.employee_rule_id
                    or data.employee_rule_id != p.rules.get("employee")
                    or selected.get("employee", (None, None))[1].source_id != "FTA17-2026"
                ):
                    raise HTTPException(
                        422, "Employee recovery requires approved date-applicable FTA17 rule"
                    )
            if data.original_invoice_id:
                original = await record(db, ctx, eng.id, data.original_invoice_id, "invoice", True)
                if (
                    original.body["profile_id"] != str(data.profile_id)
                    or original.body["direction"] != data.direction
                ):
                    raise HTTPException(422, "Credit reference outside invoice taxpayer/direction")
            for rid in set(data.net_line_ids + data.input_tax_line_ids + data.output_tax_line_ids):
                await audit.source_record(db, ctx, eng, Source(kind="journal", id=rid))
            duplicate = await db.scalar(
                select(AuditRecord.id).where(
                    AuditRecord.tenant_id == ctx.tenant_id,
                    AuditRecord.engagement_id == eng.id,
                    AuditRecord.kind == "vat-invoice",
                    AuditRecord.id != (record_id or uuid.UUID(int=0)),
                    AuditRecord.body["profile_id"].astext == str(data.profile_id),
                    AuditRecord.body["direction"].astext == data.direction,
                    AuditRecord.body["supplier_name"].astext == data.supplier_name,
                    AuditRecord.body["invoice_number"].astext == data.invoice_number,
                )
            )
            if duplicate:
                raise HTTPException(409, "Duplicate taxpayer/direction/supplier invoice reference")
        if kind == "adjustment":
            for rid in data.ledger_line_ids:
                await audit.source_record(db, ctx, eng, Source(kind="journal", id=rid))
        if kind == "einvoicing" and selected["einvoice"][1].source_id not in {
            "MD66-2026",
            "MD244-2025",
        }:
            raise HTTPException(422, "Approved official e-invoicing rollout rule required")
    for rid in evidence_ids(data.model_dump(mode="json")):
        await evidence(db, ctx, eng.id, rid)
    if kind == "return":
        await run(db, ctx, eng.id, data.run_id)
        if data.filing_state == "FILED_EXTERNALLY" and (
            not data.filing_evidence_id or not data.external_reference
        ):
            raise HTTPException(422, "External filing reference and reviewed evidence required")
    return data.model_dump(mode="json")


async def run(db, ctx, eid, rid):
    await audit.engagement(db, ctx, eid, "vat.read")
    obj = await db.scalar(
        select(VATRun).where(
            VATRun.tenant_id == ctx.tenant_id, VATRun.engagement_id == eid, VATRun.id == rid
        )
    )
    if not obj:
        raise HTTPException(404, "VAT run not found")
    return obj


async def current(db, ctx, eid, obj):
    if obj.kind == "vat201":
        profile_id = obj.inputs["profile_id"]
        for kind, key in [("invoice", "invoice_ids"), ("adjustment", "adjustment_ids")]:
            live = (
                await db.scalars(
                    select(AuditRecord.id).where(
                        AuditRecord.tenant_id == ctx.tenant_id,
                        AuditRecord.engagement_id == eid,
                        AuditRecord.kind == "vat-" + kind,
                        AuditRecord.status.in_(APPROVED),
                        AuditRecord.body["profile_id"].astext == profile_id,
                    )
                )
            ).all()
            if {str(x) for x in live} != set(obj.inputs.get(key, [])):
                return False
        source_ids = {
            uuid.UUID(x)
            for row in obj.results.get("reconciliations", [])
            for x in row["source_line_ids"]
        }
        if source_ids:
            active = await db.scalar(
                select(func.count())
                .select_from(JournalLine)
                .join(ImportBatch, ImportBatch.id == JournalLine.batch_id)
                .where(
                    JournalLine.tenant_id == ctx.tenant_id,
                    journal_ids(source_ids),
                    ImportBatch.status == "active",
                )
            )
            if active != len(source_ids):
                return False
    for item in obj.dependencies:
        row = await db.scalar(
            select(AuditRecord).where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.id == uuid.UUID(item["id"]),
            )
        )
        if not row or row.version != item["version"] or row.status not in APPROVED:
            return False
    return True


async def save(db, ctx, eid, kind, profile, inputs, dependencies, results, rid=None, key=None):
    dependencies = list({x["id"]: x for x in dependencies}.values())
    value = serial({"inputs": inputs, "dependencies": dependencies, "results": results})
    digest = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    obj = VATRun(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=eid,
        record_id=rid,
        kind=kind,
        idempotency_key=key,
        period_start=profile.period_start,
        period_end=profile.period_end,
        inputs=value["inputs"],
        dependencies=value["dependencies"],
        results=value["results"],
        sha256=digest,
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    from app.modules.audit_log.service import record as event

    event(db, ctx, "vat.calculated", obj.id, "vat", {"kind": kind, "sha256": digest})
    return obj


async def selected_records(db, ctx, eid, kind, pid):
    return (
        await db.scalars(
            select(AuditRecord)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.kind == "vat-" + kind,
                AuditRecord.status.in_(APPROVED),
                AuditRecord.body["profile_id"].astext == str(pid),
            )
            .order_by(AuditRecord.reference)
        )
    ).all()


async def invoice_result(db, ctx, eid, rid):
    obj = await record(db, ctx, eid, rid, "invoice")
    data = s.Invoice.model_validate(clean(obj.body))
    _, p, selected = await profile_inputs(db, ctx, eid, data.profile_id)
    for key in ["invoice", "output" if data.direction == "sale" else "input"]:
        applicable(selected[key][1], data.tax_point)
    return (
        obj,
        data,
        calc.transaction(
            data,
            selected["output" if data.direction == "sale" else "input"][1],
            selected["invoice"][1],
        ),
    )


async def compute(db, ctx, eid, pid):
    eng = await audit.engagement(db, ctx, eid, "vat.calculate", True)
    profile_obj, p, selected = await profile_inputs(db, ctx, eid, pid)
    applicable(selected["return"][1], p.period_start)
    invoices = await selected_records(db, ctx, eid, "invoice", pid)
    if len(invoices) > 20000:
        raise HTTPException(413, "VAT run limit20000 invoices; split period/source package")
    deps = [dep(profile_obj)] + [dep(obj) for obj, _ in selected.values()]
    line_ids = {
        uuid.UUID(str(x))
        for inv in invoices
        for key in ["net_line_ids", "output_tax_line_ids", "input_tax_line_ids"]
        for x in inv.body[key]
    }
    lines = {}
    if line_ids:
        rows = (
            await db.scalars(
                select(JournalLine).where(
                    JournalLine.tenant_id == ctx.tenant_id,
                    JournalLine.entity_id == eng.entity_id,
                    JournalLine.period_id == eng.period_id,
                    journal_ids(line_ids),
                    JournalLine.batch_id.in_(
                        select(ImportBatch.id).where(ImportBatch.status == "active")
                    ),
                )
            )
        ).all()
        lines = {str(row.id): row for row in rows}
    boxes: dict[str, dict[str, Any]] = {
        key: {"box": key, "label": label, "net": D(0), "vat": D(0)} for key, label in BOXES.items()
    }
    reconciliations = []
    exceptions: list[dict[str, Any]] = []
    seen: set[str] = set()
    sequence = set()
    evidence_set = set()
    emirates: dict[str, dict[str, Decimal]] = {}
    with localcontext() as precision:
        precision.prec = 64
        for obj in invoices:
            inv = s.Invoice.model_validate(clean(obj.body))
            treatment_rule = selected["output" if inv.direction == "sale" else "input"][1]
            applicable(treatment_rule, inv.tax_point)
            applicable(selected["invoice"][1], inv.tax_point)
            value = calc.transaction(inv, treatment_rule, selected["invoice"][1])
            issues = list(value["issues"])
            if (
                inv.rule_id != p.rules["output" if inv.direction == "sale" else "input"]
                or inv.invoice_rule_id != p.rules["invoice"]
            ):
                issues.append(
                    "Invoice approval uses different legal versions; revalidate under current selected rules"
                )
            invoice_lines = {
                str(x) for x in inv.net_line_ids + inv.output_tax_line_ids + inv.input_tax_line_ids
            }
            if seen.intersection(invoice_lines):
                issues.append("Ledger lines reused across invoices")
            seen.update(invoice_lines)
            seq = (inv.direction, inv.supplier_name, inv.sequence)
            if seq in sequence:
                issues.append("Invoice sequence collision")
            sequence.add(seq)
            if not invoice_lines <= lines.keys():
                issues.append("Source journal missing, inactive or outside taxpayer")

            def ledger(ids, credit=False):
                return sum(
                    (
                        (lines[str(x)].base_credit - lines[str(x)].base_debit)
                        * (1 if credit else -1)
                        for x in ids
                        if str(x) in lines
                    ),
                    D(0),
                )

            net_ledger = ledger(inv.net_line_ids, inv.direction == "sale")
            output_ledger = ledger(inv.output_tax_line_ids, True)
            input_ledger = ledger(inv.input_tax_line_ids)
            if (
                net_ledger != value["net"]
                or output_ledger != value["output_vat"]
                or input_ledger != value["recoverable_input"]
            ):
                issues.append("Invoice net/output/input differs from actual ledger sources")
            if inv.direction == "sale":
                box = (
                    "4"
                    if inv.treatment == "zero"
                    else "5"
                    if inv.treatment == "exempt"
                    else "1"
                    if inv.treatment in {"standard", "deemed"}
                    else None
                )
            else:
                box = (
                    "6"
                    if inv.treatment == "import_goods"
                    else "3"
                    if inv.treatment == "reverse_services"
                    else None
                )
                input_box = "10" if inv.treatment in {"import_goods", "reverse_services"} else "9"
                if value["recoverable_input"]:
                    boxes[input_box]["net"] += value["net"]
                    boxes[input_box]["vat"] += value["recoverable_input"]
            if box:
                boxes[box]["net"] += value["net"]
                boxes[box]["vat"] += value["output_vat"]
                if box == "1":
                    bucket = emirates.setdefault(inv.emirate, {"net": D(0), "vat": D(0)})
                    bucket["net"] += value["net"]
                    bucket["vat"] += value["output_vat"]
            reconciliations.append(
                {
                    "id": str(obj.id),
                    "reference": inv.invoice_number,
                    "direction": inv.direction,
                    "tax_point": str(inv.tax_point),
                    "source_amount": net_ledger,
                    "calculated_vat": value["tax"],
                    "ledger_output": output_ledger,
                    "ledger_input": input_ledger,
                    "return_output": value["output_vat"],
                    "return_input": value["recoverable_input"],
                    "difference": output_ledger
                    - input_ledger
                    - value["output_vat"]
                    + value["recoverable_input"],
                    "box": box,
                    "rule_id": str(inv.rule_id),
                    "evidence_ids": inv.evidence_record_ids,
                    "source_line_ids": sorted(invoice_lines),
                    "exception_status": "REVIEW_REQUIRED" if issues else "RECONCILED",
                }
            )
            exceptions.extend({"invoice_id": str(obj.id), "message": issue} for issue in issues)
            deps.append(dep(obj))
            evidence_set.update(evidence_ids(inv.model_dump(mode="json")))
        adjustments = await selected_records(db, ctx, eid, "adjustment", pid)
        for obj in adjustments:
            adj = s.Adjustment.model_validate(clean(obj.body))
            if not adj.statutory_conditions_confirmed:
                exceptions.append(
                    {
                        "invoice_id": str(obj.id),
                        "message": "Adjustment statutory conditions unresolved",
                    }
                )
            boxes[adj.box]["net"] += adj.net_amount
            boxes[adj.box]["vat"] += adj.tax_amount
            deps.append(dep(obj))
            evidence_set.update(evidence_ids(obj.body))
        for total, source in [("8", [str(i) for i in range(1, 8)]), ("11", ["9", "10"])]:
            for field in ["net", "vat"]:
                boxes[total][field] = sum((boxes[x][field] for x in source), D(0))
        boxes["12"]["vat"] = boxes["8"]["vat"]
        boxes["13"]["vat"] = boxes["11"]["vat"]
        boxes["14"]["vat"] = boxes["12"]["vat"] - boxes["13"]["vat"]
        control = {}
        for label, codes, credit in [
            ("output", p.output_control_codes, True),
            ("input", p.input_control_codes, False),
        ]:
            value = await db.scalar(
                select(func.coalesce(func.sum(JournalLine.base_credit - JournalLine.base_debit), 0))
                .join(Account, Account.id == JournalLine.account_id)
                .join(ImportBatch, ImportBatch.id == JournalLine.batch_id)
                .where(
                    JournalLine.tenant_id == ctx.tenant_id,
                    JournalLine.entity_id == eng.entity_id,
                    JournalLine.period_id == eng.period_id,
                    JournalLine.posting_date.between(p.period_start, p.period_end),
                    Account.code.in_(codes),
                    ImportBatch.status == "active",
                )
            )
            control[label] = D(value) if credit else -D(value)
        if control["output"] != boxes["12"]["vat"] or control["input"] != boxes["13"]["vat"]:
            exceptions.append(
                {
                    "invoice_id": None,
                    "message": "Full VAT control accounts differ from return; unmodeled or missing source transactions",
                }
            )
        for rid in evidence_set:
            deps.append(dep(await evidence(db, ctx, eid, rid)))
        result = {
            "entity_id": str(eng.entity_id),
            "currency": "AED",
            "period_start": str(p.period_start),
            "period_end": str(p.period_end),
            "profile_id": str(pid),
            "invoice_count": len(invoices),
            "boxes": list(boxes.values()),
            "emirates": emirates,
            "reconciliations": reconciliations,
            "control_accounts": control,
            "net_vat": boxes["14"]["vat"],
            "exceptions": exceptions,
            "validation": {
                "ready": not exceptions,
                "scope": "Reviewed classifications and source reconciliation; not universal VAT certification",
            },
            "filing_due": str(calc.filing_deadline(p.period_end, p.holidays)),
            "calendar_basis": p.calendar_review,
            "mapping_version": "VAT201/2022-emaratax/1.0",
            "rules": {
                key: {
                    "id": str(obj.id),
                    "version": obj.version,
                    "body": body.model_dump(mode="json"),
                    "source": SOURCES[body.source_id],
                }
                for key, (obj, body) in selected.items()
            },
            "scope": "Preparation only; no FTA submission; no automated legal classification or OCR visual verification",
        }
    return await save(
        db,
        ctx,
        eid,
        "vat201",
        p,
        {
            "profile_id": str(pid),
            "invoice_ids": [str(x.id) for x in invoices],
            "adjustment_ids": [str(x.id) for x in adjustments],
        },
        deps,
        result,
    )


async def validate_action(db, ctx, eid, obj, action):
    if (
        obj.kind in {"vat-rule", "vat-return"}
        and obj.status in APPROVED
        and action in {"return", "reopen"}
    ):
        raise HTTPException(409, "Approved legal/return history requires a new version")
    if action not in {"submit", "approve", "lock"}:
        return
    if obj.kind == "vat-invoice":
        _, _, value = await invoice_result(db, ctx, eid, obj.id)
        if not value["valid"]:
            raise HTTPException(
                409, "Invoice validation exceptions must be resolved before approval"
            )
    if obj.kind == "vat-return":
        data = s.Return.model_validate(clean(obj.body))
        result = await run(db, ctx, eid, data.run_id)
        if (
            result.kind != "vat201"
            or not data.checklist_complete
            or not result.results["validation"]["ready"]
            or not await current(db, ctx, eid, result)
        ):
            raise HTTPException(
                409, "VAT return requires a current reconciled run and completed human checklist"
            )
