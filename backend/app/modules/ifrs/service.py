import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from app.db.models.platform import Engagement, FinancialPeriod, LegalEntity
from app.modules.accounting.models import ImportBatch, ImportSnapshot
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.models import AuditRecord
from app.modules.ifrs.calculations import calculate, serial
from app.modules.ifrs.models import CalculationRun
from app.modules.ifrs.schemas import Consolidation, ReportingProfile
from app.modules.reconciliation.service import balance

D = Decimal
ZERO = D(0)
APPROVED = {"APPROVED", "LOCKED"}


def dependency(obj):
    return {"id": str(obj.id), "version": obj.version, "status": obj.status}


async def record(db, ctx, eid, rid, kind=None, approved=False):
    obj = await audit.get_record(db, ctx, eid, rid, "ifrs.read")
    if kind and obj.kind != "ifrs-" + kind:
        raise HTTPException(422, "Unexpected IFRS source record kind")
    if approved and obj.status not in APPROVED:
        raise HTTPException(409, "Approved IFRS input required")
    return obj


async def run(db, ctx, eid, rid):
    await audit.engagement(db, ctx, eid, "ifrs.read")
    result = await db.scalar(
        select(CalculationRun).where(
            CalculationRun.tenant_id == ctx.tenant_id,
            CalculationRun.engagement_id == eid,
            CalculationRun.id == rid,
        )
    )
    if not result:
        raise HTTPException(404, "Calculation run not found")
    return result


async def snapshot(db, ctx, eng, sid, comparative=False):
    obj = await db.scalar(
        select(ImportSnapshot).where(
            ImportSnapshot.id == sid, ImportSnapshot.tenant_id == ctx.tenant_id
        )
    )
    if (
        not obj
        or obj.entity_id != eng.entity_id
        or (not comparative and obj.period_id != eng.period_id)
    ):
        raise HTTPException(422, "Snapshot outside reporting entity/period")
    batch = await db.get(ImportBatch, obj.batch_id)
    if not batch or batch.status != "active":
        raise HTTPException(409, "Reporting snapshot superseded; revise and review the profile")
    return obj


async def validate_body(db, ctx, eng, kind, data):
    kind = kind.removeprefix("ifrs-")
    if kind == "profile":
        await snapshot(db, ctx, eng, data.snapshot_id)
        if data.comparative_snapshot_id:
            prior = await snapshot(db, ctx, eng, data.comparative_snapshot_id, True)
            period = await db.get(FinancialPeriod, eng.period_id)
            previous = await db.get(FinancialPeriod, prior.period_id)
            if not previous or not period or previous.end_date >= period.start_date:
                raise HTTPException(422, "Comparative period must precede current period")
        period = await db.get(FinancialPeriod, eng.period_id)
        if not period:
            raise HTTPException(422, "Financial reporting period required")
        if data.ifrs19_elected and period.start_date < date(2027, 1, 1) and not data.early_ifrs19:
            raise HTTPException(
                422, "IFRS 19 is not effective for this period without valid early election"
            )
        entity = await db.get(LegalEntity, eng.entity_id)
        if data.presentation_currency != entity.functional_currency:
            raise HTTPException(
                422,
                "Single-entity reports use functional currency; use the explicit group translation engine for a different presentation currency",
            )
    if hasattr(data, "profile_id"):
        profile = await record(db, ctx, eng.id, data.profile_id, "profile")
        values = await balance(db, ctx, uuid.UUID(profile.body["snapshot_id"]))
        codes = {r["code"] for r in values["lines"]}
        if kind == "mapping":
            if len({a.account_code for a in data.accounts}) != len(data.accounts):
                raise HTTPException(422, "Duplicate account mapping")
            if any(a.account_code not in codes for a in data.accounts):
                raise HTTPException(422, "Mapped account is outside source chart")
            definitions: dict[str, tuple] = {}
            for account in data.accounts:
                for allocation in account.allocations:
                    signature = (
                        allocation.section,
                        allocation.label,
                        allocation.note,
                        allocation.category,
                        allocation.is_cash,
                        allocation.cash_flow_role,
                    )
                    if (
                        allocation.line_code in definitions
                        and definitions[allocation.line_code] != signature
                    ):
                        raise HTTPException(
                            422, "Conflicting definitions for one presentation line"
                        )
                    definitions[allocation.line_code] = signature
        if kind == "adjustment":
            from app.modules.ifrs.catalogue import STANDARDS

            if data.standard not in STANDARDS:
                raise HTTPException(422, "Unknown standard reference")
            entity = await db.get(LegalEntity, eng.entity_id)
            period = await db.get(FinancialPeriod, eng.period_id)
            if (
                data.currency != entity.functional_currency
                or not period.start_date <= data.adjustment_date <= period.end_date
            ):
                raise HTTPException(422, "Adjustment currency/date differs from reporting scope")
            if any(leg.account_code not in codes for leg in data.legs):
                raise HTTPException(
                    422,
                    "Adjustment account is outside imported chart; import approved chart changes first",
                )
            if data.adjustment_type == "consolidation":
                raise HTTPException(422, "Group eliminations use the consolidation workbench")
            if data.adjustment_type == "prior_period":
                raise HTTPException(
                    422,
                    "Prior-period restatement requires a separate comparative reporting profile; do not post to current overlay",
                )
            if data.calculation_run_id:
                calc = await run(db, ctx, eng.id, data.calculation_run_id)
                if not calc.record_id:
                    raise HTTPException(422, "Supporting calculation record required")
                await record(db, ctx, eng.id, calc.record_id, approved=True)
            if data.reversal_of:
                previous = await record(db, ctx, eng.id, data.reversal_of, "adjustment", True)
                expected = sorted(
                    (leg["account_code"], D(leg["credit"]), D(leg["debit"]))
                    for leg in previous.body["legs"]
                )
                actual = sorted((leg.account_code, leg.debit, leg.credit) for leg in data.legs)
                if actual != expected:
                    raise HTTPException(422, "Reversal must exactly reverse approved journal legs")
        if kind == "note":
            for identifier in data.schedule_run_ids:
                await run(db, ctx, eng.id, identifier)
        if kind == "disclosure":
            from app.modules.ifrs.catalogue import STANDARDS

            if data.standard not in STANDARDS:
                raise HTTPException(422, "Unknown standard reference")
            period = await db.get(FinancialPeriod, eng.period_id)
            if data.applicability == "applicable":
                if (
                    data.standard == "IFRS 18"
                    and period.start_date < date(2027, 1, 1)
                    and not profile.body["early_ifrs18"]
                ):
                    raise HTTPException(
                        422,
                        "IFRS 18 checklist requires effective period or approved early election",
                    )
                if data.standard == "IFRS 19" and not profile.body["ifrs19_elected"]:
                    raise HTTPException(
                        422, "IFRS 19 checklist requires eligible elected reporting profile"
                    )
            if data.note_id:
                await record(db, ctx, eng.id, data.note_id, "note")
    if kind == "financials":
        calc = await run(db, ctx, eng.id, data.run_id)
        if calc.kind not in {"financials", "consolidation"}:
            raise HTTPException(422, "Financial statement calculation required")
    if kind == "lease" and data.previous_run_id:
        prior = await run(db, ctx, eng.id, data.previous_run_id)
        if prior.kind != "lease":
            raise HTTPException(422, "Prior lease calculation required")
    return data.model_dump(mode="json")


async def current_dependencies(db, ctx, eid, calculation):
    if calculation.kind == "financials":
        expected = {item["id"] for item in calculation.dependencies}
        profile_id = calculation.inputs["profile_id"]
        live = (
            await db.scalars(
                select(AuditRecord.id).where(
                    AuditRecord.tenant_id == ctx.tenant_id,
                    AuditRecord.engagement_id == eid,
                    AuditRecord.kind.in_(
                        [
                            "ifrs-mapping",
                            "ifrs-adjustment",
                            "ifrs-cash-flow",
                            "ifrs-note",
                            "ifrs-disclosure",
                        ]
                    ),
                    AuditRecord.status.in_(APPROVED),
                    AuditRecord.body["profile_id"].astext == profile_id,
                )
            )
        ).all()
        if any(str(identifier) not in expected for identifier in live):
            return False
    for item in calculation.dependencies:
        obj = await db.scalar(
            select(AuditRecord).where(
                AuditRecord.id == uuid.UUID(item["id"]), AuditRecord.tenant_id == ctx.tenant_id
            )
        )
        if not obj or obj.version != item["version"] or obj.status not in APPROVED:
            return False
        if obj.kind == "ifrs-profile":
            for field in ["snapshot_id", "comparative_snapshot_id"]:
                sid = obj.body.get(field)
                if sid:
                    snap = await db.get(ImportSnapshot, uuid.UUID(sid))
                    batch = await db.get(ImportBatch, snap.batch_id) if snap else None
                    if not batch or batch.status != "active":
                        return False
        # For group members enforce resource access, not just tenant membership.
        await audit.engagement(db, ctx, obj.engagement_id, "ifrs.read")
    return True


async def validate_action(db, ctx, eid, obj, action):
    if action == "lock":
        from app.modules.audit_execution.access import engagement_permissions

        await engagement_permissions(db, ctx, eid, "ifrs.report.lock")
    if action in {"submit", "approve", "lock"} and obj.kind == "ifrs-financials":
        calc = await run(db, ctx, eid, uuid.UUID(obj.body["run_id"]))
        if not await current_dependencies(db, ctx, eid, calc):
            raise HTTPException(
                409, "Reporting inputs changed or are no longer approved; regenerate"
            )
        if not calc.results.get("validation", {}).get("ready", False):
            raise HTTPException(409, "Financial reconciliation/disclosure controls are outstanding")


async def save_run(db, ctx, eid, kind, inputs, deps, results, record_id=None):
    payload = serial({"inputs": inputs, "dependencies": deps, "results": results})
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    obj = CalculationRun(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=eid,
        record_id=record_id,
        kind=kind,
        inputs=payload["inputs"],
        dependencies=payload["dependencies"],
        results=payload["results"],
        sha256=digest,
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    from app.modules.audit_log.service import record as event

    event(db, ctx, "ifrs.calculated", obj.id, "calculation", {"kind": kind, "sha256": digest})
    return audit.serialize(obj)


async def calculate_record(db, ctx, eid, rid):
    await audit.engagement(db, ctx, eid, "ifrs.calculation.execute", True)
    obj = await record(db, ctx, eid, rid, approved=True)
    kind = obj.kind.removeprefix("ifrs-")
    from app.modules.ifrs.calculations import ENGINES

    if kind not in ENGINES:
        raise HTTPException(422, "No standalone numeric engine for this record")
    body = {
        k: v
        for k, v in obj.body.items()
        if k not in {"review_stage", "review_cycle", "review_approvers"}
    }
    try:
        results = calculate(kind, body)
    except (ValueError, ArithmeticError) as exc:
        raise HTTPException(422, str(exc)) from None
    deps = [dependency(obj)]
    if kind == "lease" and body.get("previous_run_id"):
        prior = await run(db, ctx, eid, uuid.UUID(body["previous_run_id"]))
        if not await current_dependencies(db, ctx, eid, prior):
            raise HTTPException(409, "Prior lease assumptions changed")
        rows = [r for r in prior.results["schedule"] if r["date"] <= body["commencement"]]
        previous_balance = D(rows[-1]["closing"]) if rows else D(prior.results["initial_liability"])
        previous_date = (
            date.fromisoformat(rows[-1]["date"])
            if rows
            else date.fromisoformat(prior.inputs["commencement"])
        )
        from app.modules.ifrs.calculations import growth

        previous_balance *= growth(
            D(prior.inputs["annual_discount_rate"]),
            (date.fromisoformat(body["commencement"]) - previous_date).days,
        )
        results["remeasurement"] = {
            "prior_run_id": str(prior.id),
            "previous_carrying": str(previous_balance),
            "liability_delta": str(D(results["initial_liability"]) - previous_balance),
            "reason": body["remeasurement_reason"],
            "journal_treatment": "Human modification classification required",
        }
        deps += prior.dependencies
    return await save_run(db, ctx, eid, kind, body, deps, results, obj.id)


async def approved_inputs(db, ctx, eid, kind, profile_id):
    return (
        await db.scalars(
            select(AuditRecord)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.kind == "ifrs-" + kind,
                AuditRecord.status.in_(APPROVED),
                AuditRecord.body["profile_id"].astext == str(profile_id),
            )
            .order_by(AuditRecord.created_at)
        )
    ).all()


async def adjusted_balance(db, ctx, eid, profile_id, comparative=False):
    profile = await record(db, ctx, eid, profile_id, "profile", True)
    data = ReportingProfile.model_validate(
        {k: v for k, v in profile.body.items() if not k.startswith("review_")}
    )
    sid = data.comparative_snapshot_id if comparative else data.snapshot_id
    if not sid:
        raise HTTPException(409, "Comparative snapshot not supplied")
    eng = await audit.engagement(db, ctx, eid)
    await snapshot(db, ctx, eng, sid, comparative)
    tb = await balance(db, ctx, sid)
    values = {r["code"]: {**r, "original": r["closing"], "adjustment": ZERO} for r in tb["lines"]}
    adjustments = (
        [] if comparative else await approved_inputs(db, ctx, eid, "adjustment", profile.id)
    )
    supporting_deps = []
    for adjustment in adjustments:
        if adjustment.body.get("calculation_run_id"):
            supporting = await run(db, ctx, eid, uuid.UUID(adjustment.body["calculation_run_id"]))
            supporting_deps += supporting.dependencies
            if not await current_dependencies(db, ctx, eid, supporting):
                raise HTTPException(
                    409, "Adjustment supporting assumptions changed; reopen and reassess"
                )
        for leg in adjustment.body["legs"]:
            if leg["account_code"] not in values:
                raise HTTPException(409, "Source chart changed; adjustment cannot be applied")
            values[leg["account_code"]]["adjustment"] += D(leg["debit"]) - D(leg["credit"])
    for r in values.values():
        r["adjusted"] = r["original"] + r["adjustment"]
    return (
        profile,
        tb,
        list(values.values()),
        [dependency(profile)] + [dependency(a) for a in adjustments] + supporting_deps,
    )


async def financials(db, ctx, eid, profile_id):
    await audit.engagement(db, ctx, eid, "ifrs.financials.prepare", True)
    profile, tb, accounts, deps = await adjusted_balance(db, ctx, eid, profile_id)
    mappings = await approved_inputs(db, ctx, eid, "mapping", profile.id)
    if len(mappings) != 1:
        raise HTTPException(
            409,
            "Exactly one approved mapping version per reporting profile is required; reopen superseded mapping before approval",
        )
    mapping = mappings[0]
    deps.append(dependency(mapping))
    mapped = {a["account_code"]: a for a in mapping.body["accounts"]}
    missing = [
        r["code"]
        for r in accounts
        if (r["original"] or r["opening"] or r["adjustment"]) and r["code"] not in mapped
    ]
    if missing:
        raise HTTPException(409, "Unmapped nonzero accounts: " + ", ".join(missing[:20]))
    comparative: dict[str, Decimal] = {}
    comparative_meta = None
    if profile.body.get("comparative_snapshot_id"):
        comparative_id = profile.body.get("comparative_profile_id")
        if not comparative_id:
            raise HTTPException(
                409, "Comparatives require a separately approved source reporting profile"
            )
        previous_eid = (
            uuid.UUID(profile.body["comparative_engagement_id"])
            if profile.body.get("comparative_engagement_id")
            else eid
        )
        previous_profile, prior_tb, prior_rows, prior_deps = await adjusted_balance(
            db, ctx, previous_eid, uuid.UUID(comparative_id)
        )
        if str(previous_profile.body["snapshot_id"]) != profile.body["comparative_snapshot_id"]:
            raise HTTPException(422, "Comparative profile/snapshot mismatch")
        previous_mapping = await approved_inputs(
            db, ctx, previous_eid, "mapping", previous_profile.id
        )
        if len(previous_mapping) != 1:
            raise HTTPException(409, "Approved comparative mapping required")
        previous_rules = {a["account_code"]: a for a in previous_mapping[0].body["accounts"]}
        for row in prior_rows:
            if row["code"] not in previous_rules and row["adjusted"]:
                raise HTTPException(409, "Unmapped comparative balance")
            for allocation in previous_rules.get(row["code"], {}).get("allocations", []):
                comparative[allocation["line_code"]] = comparative.get(
                    allocation["line_code"], ZERO
                ) + row["adjusted"] * D(allocation["weight"])
        deps += prior_deps + [dependency(previous_mapping[0])]
        comparative_meta = {
            "profile_id": str(previous_profile.id),
            "snapshot_id": profile.body["comparative_snapshot_id"],
        }
    lines: dict[str, Any] = {}
    for account in accounts:
        for allocation in mapped.get(account["code"], {}).get("allocations", []):
            code = allocation["line_code"]
            row = lines.setdefault(
                code,
                {
                    **allocation,
                    "current": ZERO,
                    "opening": ZERO,
                    "comparative": comparative.get(code, ZERO),
                    "source_accounts": [],
                },
            )
            weight = D(allocation["weight"])
            row["current"] += account["adjusted"] * weight
            row["opening"] += account["opening"] * weight
            row["source_accounts"].append(
                {
                    "code": account["code"],
                    "original": account["original"],
                    "adjustment": account["adjustment"],
                    "weight": weight,
                    "allocated": account["adjusted"] * weight,
                }
            )
    # Comparative-only rows remain visible instead of being silently dropped.
    if comparative:
        for a in previous_mapping[0].body["accounts"]:
            for allocation in a["allocations"]:
                code = allocation["line_code"]
                if code not in lines:
                    lines[code] = {
                        **allocation,
                        "current": ZERO,
                        "opening": ZERO,
                        "comparative": comparative.get(code, ZERO),
                        "source_accounts": [],
                    }

    def total(section, column="current"):
        return sum((r[column] for r in lines.values() if r["section"] == section), ZERO)

    profit = -total("income") - total("expenses")
    oci = -total("oci")
    assets = total("assets")
    liabilities = -total("liabilities")
    equity = -total("equity") + profit + oci
    cash = sum((r["current"] for r in lines.values() if r["is_cash"]), ZERO)
    opening_cash = sum((r["opening"] for r in lines.values() if r["is_cash"]), ZERO)
    working_capital = sum(
        (
            -(r["current"] - r["opening"])
            if r["cash_flow_role"] == "working_capital_asset"
            else -(r["current"] - r["opening"])
            if r["cash_flow_role"] == "working_capital_liability"
            else ZERO
            for r in lines.values()
        ),
        ZERO,
    )
    cash_records = await approved_inputs(db, ctx, eid, "cash-flow", profile.id)
    cash_schedule = None
    if len(cash_records) == 1:
        cf = cash_records[0]
        b = cf.body
        deps.append(dependency(cf))
        operating = (
            profit + D(b["noncash_adjustments"]) + working_capital
            if b["method"] == "indirect"
            else D(b["direct_operating_receipts"]) - D(b["direct_operating_payments"])
        )
        closing = (
            opening_cash
            + operating
            + D(b["investing"])
            + D(b["financing"])
            + D(b["exchange_effect"])
        )
        cash_schedule = {
            "method": b["method"],
            "opening": opening_cash,
            "profit": profit,
            "noncash_adjustments": D(b["noncash_adjustments"]),
            "working_capital": working_capital,
            "operating": operating,
            "investing": D(b["investing"]),
            "financing": D(b["financing"]),
            "exchange_effect": D(b["exchange_effect"]),
            "closing": closing,
            "source_cash": cash,
            "difference": closing - cash,
            "policy": b["policy"],
        }
    notes = await approved_inputs(db, ctx, eid, "note", profile.id)
    disclosures = await approved_inputs(db, ctx, eid, "disclosure", profile.id)
    deps += [dependency(r) for r in notes + disclosures]
    note_rows = []
    for note in notes:
        codes = note.body["linked_line_codes"]
        if any(code not in lines for code in codes):
            raise HTTPException(409, "Note references an unknown statement line")
        schedules = []
        for rid in note.body["schedule_run_ids"]:
            schedule = await run(db, ctx, eid, uuid.UUID(rid))
            if not await current_dependencies(db, ctx, eid, schedule):
                raise HTTPException(409, "Supporting note schedule changed")
            schedules.append(
                {"id": str(schedule.id), "kind": schedule.kind, "results": schedule.results}
            )
            deps += schedule.dependencies
        note_rows.append(
            {
                "id": str(note.id),
                "reference": note.body["note_reference"],
                "text": note.body["text"],
                "ai_authored": note.body["ai_authored"],
                "lines": [
                    {
                        "code": code,
                        "current": lines[code]["current"],
                        "comparative": lines[code]["comparative"],
                    }
                    for code in codes
                ],
                "supporting_schedules": schedules,
            }
        )
    note_refs = {n["reference"] for n in note_rows}
    missing_notes = sorted(
        {r["note"] for r in lines.values() if r["current"] or r["comparative"]} - note_refs
    )
    # Original category checklist is a scoped aid, never a full copyrighted disclosure checklist.
    needed = {"presentation", "policies", "judgments", "events_after_reporting", "going_concern"}
    needed |= {r["note"] for r in lines.values() if r["current"] or r["comparative"]}
    answered = {
        d.body["category"]
        for d in disclosures
        if d.body["applicability"] != "unknown"
        and (
            d.body["applicability"] == "not_applicable"
            or d.body.get("note_id") in {str(n.id) for n in notes}
        )
    }
    checks = [
        {"code": "source_trial_balance", "passed": tb["balanced"]},
        {
            "code": "accounting_equation",
            "passed": assets - liabilities - equity == 0,
            "difference": assets - liabilities - equity,
        },
        {
            "code": "adjusted_trial_balance",
            "passed": sum((r["adjusted"] for r in accounts), ZERO) == 0,
        },
        {
            "code": "cash_flow_reconciliation",
            "passed": cash_schedule is not None and cash_schedule["difference"] == 0,
        },
        {"code": "notes_reconciled", "passed": not missing_notes, "missing": missing_notes},
        {
            "code": "disclosures_assessed",
            "passed": needed <= answered,
            "missing": sorted(needed - answered),
        },
        {"code": "single_cash_flow_policy", "passed": len(cash_records) == 1},
        {
            "code": "comparative_opening_consistency",
            "passed": comparative_meta is None
            or all(
                r["opening"] == r["comparative"]
                for r in lines.values()
                if r["section"] in {"assets", "liabilities", "equity"}
            ),
        },
        {
            "code": "comparative_source",
            "passed": not profile.body.get("comparative_snapshot_id")
            or comparative_meta is not None,
        },
    ]
    eng = await db.get(Engagement, eid)
    period = await db.get(FinancialPeriod, eng.period_id)
    entity = await db.get(LegalEntity, eng.entity_id)
    presentation = (
        "IFRS 18"
        if period.start_date >= date(2027, 1, 1) or profile.body["early_ifrs18"]
        else "IAS 1"
    )
    subtotal = {
        cat: -sum(
            (
                r["current"]
                for r in lines.values()
                if r["section"] in {"income", "expenses"} and r["category"] == cat
            ),
            ZERO,
        )
        for cat in ["operating", "investing", "financing", "tax", "discontinued"]
    }
    results = {
        "entity": entity.name,
        "presentation_settings": {
            "suppress_zero": profile.body["suppress_zero"],
            "materiality": profile.body["presentation_materiality"],
            "precision": profile.body["rounding_precision"],
        },
        "entity_id": str(entity.id),
        "period_start": str(period.start_date),
        "period_end": str(period.end_date),
        "currency": profile.body["presentation_currency"],
        "precision": profile.body["rounding_precision"],
        "presentation": presentation,
        "ifrs19_profile": "reduced-disclosure-original/1"
        if profile.body["ifrs19_elected"]
        else "full-disclosure-original/1",
        "lines": list(lines.values()),
        "adjusted_trial_balance": accounts,
        "totals": {
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity,
            "profit": profit,
            "oci": oci,
            "total_comprehensive_income": profit + oci,
            "cash": cash,
        },
        "profit_categories": subtotal,
        "changes_in_equity": {
            "opening": -total("equity", "opening"),
            "profit": profit,
            "oci": oci,
            "direct_equity_movements": -total("equity") + total("equity", "opening"),
            "closing": equity,
        },
        "cash_flow": cash_schedule,
        "notes": note_rows,
        "comparative": comparative_meta,
        "validation": {
            "checks": checks,
            "ready": all(c["passed"] for c in checks),
            "ifrs_compliance_certified": False,
        },
        "scope": "Mapped full-IFRS general corporate statements; human classification, elections, disclosures and professional review required",
    }
    return await save_run(
        db,
        ctx,
        eid,
        "financials",
        {"profile_id": str(profile.id), "snapshot_id": profile.body["snapshot_id"]},
        deps,
        results,
    )


async def consolidate(db, ctx, eid, rid):
    await audit.engagement(db, ctx, eid, "ifrs.consolidation.prepare", True)
    obj = await record(db, ctx, eid, rid, "consolidation", True)
    data = Consolidation.model_validate(
        {k: v for k, v in obj.body.items() if not k.startswith("review_")}
    )
    if (
        len({m.engagement_id for m in data.members}) != len(data.members)
        or sum(m.acquisition_type == "parent" for m in data.members) != 1
    ):
        raise HTTPException(422, "One parent and unique entity packages required")
    lines: dict[str, Any] = {}
    deps = [dependency(obj)]
    members = []
    nci = ZERO
    goodwill = ZERO
    periods = set()
    for member in data.members:
        await audit.engagement(db, ctx, member.engagement_id, "ifrs.read")
        calc = await run(db, ctx, member.engagement_id, member.financial_run_id)
        if calc.kind != "financials" or not await current_dependencies(
            db, ctx, member.engagement_id, calc
        ):
            raise HTTPException(409, "Current individual financial package required")
        approvals = (
            await db.scalars(
                select(AuditRecord).where(
                    AuditRecord.tenant_id == ctx.tenant_id,
                    AuditRecord.engagement_id == member.engagement_id,
                    AuditRecord.kind == "ifrs-financials",
                    AuditRecord.status.in_(APPROVED),
                    AuditRecord.body["run_id"].astext == str(calc.id),
                )
            )
        ).all()
        if not approvals:
            raise HTTPException(409, "Approved entity reporting package required")
        if member.acquisition_type not in {"parent", "business_combination"}:
            raise HTTPException(
                422,
                "Common-control, asset-acquisition and equity-method packages require a separately validated policy implementation; no automatic IFRS 3 treatment",
            )
        if member.acquisition_type != "parent" and not (
            member.power and member.variable_returns and member.ability_to_affect_returns
        ):
            raise HTTPException(422, "IFRS 10 control assessment is not established")
        periods.add((calc.results["period_start"], calc.results["period_end"]))
        if member.rate_date != date.fromisoformat(calc.results["period_end"]):
            raise HTTPException(422, "Rate effective date must match reporting date")
        deps += calc.dependencies + [dependency(a) for a in approvals]
        translated = ZERO
        net_assets = ZERO
        for row in calc.results["lines"]:
            rate = (
                member.closing_rate
                if row["section"] in {"assets", "liabilities"}
                else member.historical_rate
                if row["section"] == "equity"
                else member.average_rate
            )
            value = D(row["current"]) * rate
            previous = lines.get(row["line_code"])
            if previous and previous["section"] != row["section"]:
                raise HTTPException(422, "Group chart line has conflicting sections")
            target = lines.setdefault(
                row["line_code"],
                {
                    **row,
                    "current": ZERO,
                    "comparative": ZERO,
                    "opening": ZERO,
                    "source_accounts": [],
                },
            )
            target["current"] += value
            translated += value
            if row["section"] in {"assets", "liabilities"}:
                net_assets += value
            target["source_accounts"].append(
                {
                    "engagement_id": str(member.engagement_id),
                    "run_id": str(calc.id),
                    "source_amount": row["current"],
                    "rate": rate,
                    "translated": value,
                    "rate_source": member.rate_source,
                }
            )
        # Translation balancing reserve is an explicit OCI/equity movement, never an FX plug hidden in cash.
        reserve = lines.setdefault(
            "FX_TRANSLATION",
            {
                "line_code": "FX_TRANSLATION",
                "label": "Foreign operation translation reserve",
                "section": "oci",
                "category": "operating",
                "note": "translation",
                "current": ZERO,
                "comparative": ZERO,
                "opening": ZERO,
                "source_accounts": [],
            },
        )
        reserve["current"] -= translated
        share = (1 - member.ownership) * net_assets if member.acquisition_type != "parent" else ZERO
        nci += share
        gw = (
            member.consideration + member.nci_at_acquisition - member.net_assets_at_acquisition
            if member.acquisition_type == "business_combination"
            else ZERO
        )
        goodwill += gw
        members.append(
            {
                "engagement_id": str(member.engagement_id),
                "ownership": member.ownership,
                "translated_net_assets": net_assets,
                "nci_closing": share,
                "acquisition_goodwill_or_bargain_purchase": gw,
            }
        )
    if len(periods) != 1:
        raise HTTPException(
            422, "Different reporting dates require approved date-alignment packages"
        )
    for elimination in data.eliminations:
        if elimination.debit_line not in lines or elimination.credit_line not in lines:
            raise HTTPException(422, "Elimination line not in group chart")
        for identifier in elimination.source_record_ids:
            source = await db.scalar(
                select(AuditRecord).where(
                    AuditRecord.tenant_id == ctx.tenant_id, AuditRecord.id == identifier
                )
            )
            if (
                not source
                or source.engagement_id not in {m.engagement_id for m in data.members}
                or source.status not in APPROVED
            ):
                raise HTTPException(422, "Approved scoped elimination evidence/source required")
            await audit.engagement(db, ctx, source.engagement_id, "ifrs.read")
            deps.append(dependency(source))
        lines[elimination.debit_line]["current"] += elimination.amount
        lines[elimination.credit_line]["current"] -= elimination.amount
    if data.unrealised_profit:
        if (
            not data.unrealised_profit_source.strip()
            or data.unrealised_profit_inventory_line not in lines
            or data.unrealised_profit_expense_line not in lines
        ):
            raise HTTPException(422, "Documented unrealised-profit accounts/source required")
        lines[data.unrealised_profit_inventory_line]["current"] -= data.unrealised_profit
        lines[data.unrealised_profit_expense_line]["current"] += data.unrealised_profit
    totals = {
        section: sum((r["current"] for r in lines.values() if r["section"] == section), ZERO)
        for section in ["assets", "liabilities", "equity", "income", "expenses", "oci"]
    }
    profit = -totals["income"] - totals["expenses"]
    equity = -totals["equity"] + profit - totals["oci"]
    difference = totals["assets"] + totals["liabilities"] - equity
    results = {
        "entity": "Consolidated group",
        "period_start": next(iter(periods))[0],
        "period_end": next(iter(periods))[1],
        "currency": data.presentation_currency,
        "precision": 2,
        "presentation": "Group corporate presentation",
        "lines": list(lines.values()),
        "members": members,
        "eliminations": [e.model_dump(mode="json") for e in data.eliminations],
        "totals": {
            "assets": totals["assets"],
            "liabilities": -totals["liabilities"],
            "equity": equity,
            "profit": profit,
            "oci": -totals["oci"],
            "nci": nci,
            "parent_equity": equity - nci,
        },
        "acquisition_schedule": {
            "goodwill_or_bargain_purchase_total": goodwill,
            "posting": "Acquisition journals must be explicitly supplied; schedule is not silently posted",
        },
        "validation": {
            "checks": [
                {
                    "code": "group_accounting_equation",
                    "passed": difference == 0,
                    "difference": difference,
                }
            ],
            "ready": False,
            "ifrs_compliance_certified": False,
        },
        "scope": "Full aggregation of approved controlled packages; explicit eliminations and rate translation. Draft only until group notes/cash-flow/acquisition and professional validation are complete",
    }
    return await save_run(db, ctx, eid, "consolidation", obj.body, deps, results, obj.id)
