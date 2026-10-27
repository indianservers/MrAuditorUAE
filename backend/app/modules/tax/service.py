import hashlib
import json
import uuid
from calendar import monthrange
from datetime import date
from decimal import Decimal, localcontext
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.db.models.platform import Engagement, FinancialPeriod, LegalEntity
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.models import AuditRecord, EvidenceVersion
from app.modules.ifrs import service as ifrs
from app.modules.ifrs.calculations import serial
from app.modules.tax import calculations as calc
from app.modules.tax import schemas as s
from app.modules.tax.catalogue import SOURCES
from app.modules.tax.models import LossPosting, TaxRelease, TaxRun

D = Decimal
ZERO = D(0)
APPROVED = {"APPROVED", "LOCKED"}


def clean(body):
    return {k: v for k, v in body.items() if not k.startswith("review_")}


async def record(db, ctx, eid, rid, kind=None, approved=False):
    obj = await audit.get_record(db, ctx, eid, rid, "tax.profile.read")
    if not obj.kind.startswith("tax-") or kind and obj.kind != "tax-" + kind:
        raise HTTPException(422, "Unexpected tax record kind")
    if approved and obj.status not in APPROVED:
        raise HTTPException(409, "Approved tax input required")
    if approved:
        from app.modules.lineage.working_papers import require_context_current

        await require_context_current(db, ctx, obj)
    return obj


async def run(db, ctx, eid, rid):
    await audit.engagement(db, ctx, eid, "tax.profile.read")
    obj = await db.scalar(
        select(TaxRun).where(
            TaxRun.tenant_id == ctx.tenant_id, TaxRun.engagement_id == eid, TaxRun.id == rid
        )
    )
    if not obj:
        raise HTTPException(404, "Tax run not found")
    return obj


async def evidence(db, ctx, eid, rid):
    obj = await audit.get_record(db, ctx, eid, rid, "tax.profile.read")
    if obj.status not in APPROVED:
        raise HTTPException(
            409, "Independently approved supporting evidence/working paper required"
        )
    if obj.kind == "evidence":
        version = await db.scalar(
            select(EvidenceVersion)
            .where(EvidenceVersion.tenant_id == ctx.tenant_id, EvidenceVersion.record_id == obj.id)
            .order_by(EvidenceVersion.number.desc())
            .limit(1)
        )
        if not version or version.scan_status != "CLEAN":
            raise HTTPException(409, "Clean scanned supporting evidence required")
    return obj


async def financial_source(db, ctx, eid, rid):
    result = await ifrs.run(db, ctx, eid, rid)
    if result.kind != "financials" or not await ifrs.current_dependencies(db, ctx, eid, result):
        raise HTTPException(409, "Current individual IFRS financial package required")
    approvals = (
        await db.scalars(
            select(AuditRecord).where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.kind == "ifrs-financials",
                AuditRecord.status.in_(APPROVED),
                AuditRecord.body["run_id"].astext == str(rid),
            )
        )
    ).all()
    if not approvals:
        raise HTTPException(409, "Independent IFRS financial-package approval required")
    return result, list(result.dependencies) + [ifrs.dependency(x) for x in approvals]


async def applicable_rule(db, ctx, eid, rid, profile, category=None):
    obj = await record(db, ctx, eid, rid, "rule", True)
    rule = s.Rule.model_validate(clean(obj.body))
    if (
        rule.lifecycle != "ACTIVE"
        or rule.effective_from > profile.tax_start
        or rule.effective_to
        and rule.effective_to < profile.tax_end
        or rule.known_from > profile.legal_as_of
    ):
        raise HTTPException(
            409, "Rule is not approved/applicable/known for this tax period and legal as-of date"
        )
    if category and rule.category != category:
        raise HTTPException(422, "Rule category does not match tax calculation")
    if rule.source_id == "MD131-2026" and rule.parameters.sbr_last_period_end > date(2026, 12, 31):
        from datetime import timedelta

        if (
            not rule.publication_date
            or not rule.publication_evidence_id
            or profile.legal_as_of < rule.publication_date + timedelta(days=1)
        ):
            raise HTTPException(
                409,
                "MD131 extension requires reviewed publication evidence and legal knowledge after commencement",
            )
        await evidence(db, ctx, eid, rule.publication_evidence_id)
    return obj, rule


async def validate_body(db, ctx, eng, kind, data, record_id=None):
    kind = kind.removeprefix("tax-")
    if kind == "rule":
        if data.source_id not in SOURCES:
            raise HTTPException(422, "Only registered official source IDs may support rules")
        source = SOURCES[data.source_id]
        if data.article and data.article not in source["articles"]:
            raise HTTPException(422, "Article is not verified in the registered source")
        if data.source_id == "MD131-2026" and data.parameters.sbr_last_period_end > date(
            2026, 12, 31
        ):
            if (
                data.parameters.sbr_last_period_end != date(2029, 12, 31)
                or not data.publication_date
                or not data.publication_evidence_id
                or not data.source_sha256
            ):
                raise HTTPException(
                    409,
                    "Verify MD131 publication and retained source before adopting the 2029 end-date extension",
                )
            await evidence(db, ctx, eng.id, data.publication_evidence_id)
        issued = {
            "MD131-2026": date(2026, 7, 29),
            "MD229-2025": date(2025, 8, 28),
            "FTA6-2026": date(2026, 6, 2),
        }.get(data.source_id)
        if issued and data.known_from < issued:
            raise HTTPException(422, "Legal knowledge date cannot precede verified issuance")
        duplicate = await db.scalar(
            select(AuditRecord.id)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eng.id,
                AuditRecord.kind == "tax-rule",
                AuditRecord.id != (record_id or uuid.UUID(int=0)),
                AuditRecord.body["rule_key"].astext == data.rule_key,
                AuditRecord.body["rule_version"].astext == str(data.rule_version),
            )
            .limit(1)
        )
        # Same-key version changes must be a new record, not overwritten legal history.
        if duplicate:
            raise HTTPException(409, "Rule key/version already exists; create a new rule version")
    if kind == "profile":
        period = await db.get(FinancialPeriod, eng.period_id)
        if data.tax_start != period.start_date or data.tax_end != period.end_date:
            raise HTTPException(
                422, "Separate or misaligned tax periods require a validated alignment package"
            )
        financial, _ = await financial_source(db, ctx, eng.id, data.financial_run_id)
        if financial.results["currency"] != "AED":
            raise HTTPException(
                422,
                "Tax computation requires an approved AED reporting package; no unsourced conversion",
            )
        source_revenue = -sum(
            (
                D(line["current"])
                for line in financial.results["lines"]
                if line["section"] == "income"
            ),
            ZERO,
        )
        if data.revenue != source_revenue + data.revenue_reconciliation_adjustment:
            raise HTTPException(
                422,
                "Tax revenue does not reconcile to approved IFRS income and explicit revenue bridge",
            )
        if data.revenue_reconciliation_adjustment:
            if not data.revenue_adjustment_evidence_id:
                raise HTTPException(422, "Tax revenue bridge evidence required")
            await evidence(db, ctx, eng.id, data.revenue_adjustment_evidence_id)
        if data.classification in {"resident_juridical", "qfzp"} and not data.resident:
            raise HTTPException(422, "Resident classification contradicts residence facts")
        if data.classification == "qfzp" and not data.free_zone:
            raise HTTPException(422, "QFZP profile requires Free Zone Person facts")
        for category, rid in data.rules.items():
            await applicable_rule(db, ctx, eng.id, rid, data, category)
        if not {"standard", "adjustments", "losses", "deadline"} <= set(data.rules):
            raise HTTPException(
                422, "Standard, adjustments, losses and deadline rule versions required"
            )
        if data.audited_financials_evidence_id:
            await evidence(db, ctx, eng.id, data.audited_financials_evidence_id)
    if hasattr(data, "profile_id"):
        obj = await record(db, ctx, eng.id, data.profile_id, "profile")
        profile = s.TaxProfile.model_validate(clean(obj.body))
        if hasattr(data, "rule_id"):
            await applicable_rule(db, ctx, eng.id, data.rule_id, profile)
        ids: list[uuid.UUID] = []
        for field in ["evidence_record_ids"]:
            ids += getattr(data, field, [])
        for field in [
            "election_evidence_id",
            "contract_evidence_id",
            "governance_evidence_id",
            "application_evidence_id",
            "approval_evidence_id",
            "valuation_evidence_id",
            "evidence_record_id",
            "fta_application_evidence_id",
            "fta_approval_evidence_id",
            "special_purpose_audit_evidence_id",
        ]:
            value = getattr(data, field, None)
            if value:
                ids.append(value)
        for condition in getattr(data, "conditions", []):
            ids += condition.evidence_record_ids
        for row in getattr(data, "segments", []):
            ids.append(row.contract_evidence_id)
        for rid in set(ids):
            await evidence(db, ctx, eng.id, rid)
        if kind in {"restructuring", "transitional"}:
            _, legal = await applicable_rule(db, ctx, eng.id, data.rule_id, profile)
            article = (
                "61"
                if kind == "transitional"
                else "26"
                if data.relief_type == "qualifying_group"
                else "27"
            )
            if legal.source_id != "CT-LAW" or legal.article != article:
                raise HTTPException(
                    422, "Assessment requires the correct approved statutory article"
                )
        if kind in {"qfzp", "credit", "interest"}:
            financial, _ = await financial_source(db, ctx, eng.id, profile.financial_run_id)
            income_lines = {
                x["line_code"]: abs(D(x["current"]))
                for x in financial.results["lines"]
                if x["section"] == "income"
            }
            if kind == "qfzp":
                if (
                    data.distribution_activity
                    and profile.tax_start >= date(2026, 1, 1)
                    and profile.legal_as_of >= date(2026, 6, 2)
                ):
                    if not data.procedures_rule_id:
                        raise HTTPException(
                            422,
                            "Distribution assessment requires approved FTA6/2026 procedures rule",
                        )
                    _, procedure = await applicable_rule(
                        db, ctx, eng.id, data.procedures_rule_id, profile
                    )
                    if procedure.source_id != "FTA6-2026":
                        raise HTTPException(422, "Incorrect distribution procedures source")
                segmented: dict[str, Decimal] = {}
                for segment in data.segments:
                    code = segment.source_line_code
                    if code not in income_lines:
                        raise HTTPException(422, "QFZP segment must trace to approved income line")
                    segmented[code] = segmented.get(code, ZERO) + segment.revenue
                if any(value > income_lines[code] for code, value in segmented.items()):
                    raise HTTPException(
                        422, "Segment revenue exceeds its approved financial source"
                    )
            if kind == "credit":
                if any(
                    code not in income_lines for code in data.source_line_codes
                ) or data.foreign_taxable_income > sum(
                    (income_lines[code] for code in set(data.source_line_codes)), ZERO
                ):
                    raise HTTPException(422, "Foreign income exceeds approved income source")
            if kind == "interest":
                codes = set(data.source_account_codes)
                accounts = {
                    x["code"]: abs(D(x["adjusted"]))
                    for x in financial.results["adjusted_trial_balance"]
                }
                if not codes or not data.evidence_record_ids or not codes <= accounts.keys():
                    raise HTTPException(
                        422, "Interest requires approved source accounts and evidence"
                    )
                if data.interest_expense + data.interest_income > sum(
                    (accounts[code] for code in codes), ZERO
                ):
                    raise HTTPException(422, "Interest exceeds selected approved source balances")
        if kind == "adjustment":
            if data.source_engagement_id and data.source_engagement_id != eng.id:
                raise HTTPException(422, "Individual tax adjustment source engagement mismatch")
            _, rule = await applicable_rule(db, ctx, eng.id, data.rule_id, profile, "adjustments")
            financial, _ = await financial_source(db, ctx, eng.id, profile.financial_run_id)
            accounts = {
                r["code"]: D(r["adjusted"]) for r in financial.results["adjusted_trial_balance"]
            }
            if any(code not in accounts for code in data.account_codes):
                raise HTTPException(422, "Tax adjustment account outside approved IFRS source")
            if abs(data.accounting_amount) > sum(
                (abs(accounts[code]) for code in set(data.account_codes)), ZERO
            ):
                raise HTTPException(
                    422, "Adjustment accounting amount exceeds selected source balances"
                )
            try:
                calc.adjustment_amount(data, rule.parameters)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
            required_article = {
                "entertainment": "29",
                "fine": "33",
                "nondeductible": "33",
                "nonbusiness": "28",
            }.get(data.category)
            if required_article and (
                rule.source_id != "CT-LAW" or rule.article != required_article
            ):
                raise HTTPException(
                    422, "Statutory expense category requires its correct approved CT Law article"
                )
            if data.ai_suggestion_id:
                suggestion = await record(db, ctx, eng.id, data.ai_suggestion_id, "ai")
                if suggestion.status != "ACCEPTED":
                    raise HTTPException(409, "AI suggestion must be independently accepted first")
        if kind == "credit":
            _, credit_rule = await applicable_rule(
                db, ctx, eng.id, data.rule_id, profile, "exemption"
            )
            if credit_rule.source_id != "CT-LAW" or credit_rule.article != "47":
                raise HTTPException(422, "Foreign tax credit requires approved Article47 rule")
            _, standard_rule = await applicable_rule(
                db, ctx, eng.id, profile.rules["standard"], profile, "standard"
            )
            if (
                data.uae_tax_attributable
                > data.foreign_taxable_income * standard_rule.parameters.standard_rate
            ):
                raise HTTPException(
                    422, "Attributed UAE tax exceeds maximum tax on the foreign taxable income"
                )
        if kind == "loss":
            await db.scalar(
                select(LegalEntity)
                .where(LegalEntity.tenant_id == ctx.tenant_id, LegalEntity.id == eng.entity_id)
                .with_for_update()
            )
            if data.origin_end >= profile.tax_start or data.origin_end < data.origin_start:
                raise HTTPException(422, "Loss must originate in an earlier tax period")
            if data.origin_start < date(2023, 6, 1) or data.excluded_pre_ct_or_exempt:
                raise HTTPException(422, "Excluded pre-CT/exempt losses are not available")
            if data.origin_tax_run_id:
                origin = await db.scalar(
                    select(TaxRun).where(
                        TaxRun.tenant_id == ctx.tenant_id, TaxRun.id == data.origin_tax_run_id
                    )
                )
                if not origin:
                    raise HTTPException(422, "Origin tax run not found")
                origin_eng = await audit.engagement(
                    db, ctx, origin.engagement_id, "tax.profile.read"
                )
                if (
                    origin_eng.entity_id != eng.entity_id
                    or D(origin.results.get("current_tax_loss", "0")) != data.amount
                ):
                    raise HTTPException(422, "Loss differs from source tax computation")
            duplicate = await db.scalar(
                select(AuditRecord.id)
                .join(Engagement, Engagement.id == AuditRecord.engagement_id)
                .where(
                    AuditRecord.tenant_id == ctx.tenant_id,
                    Engagement.entity_id == eng.entity_id,
                    AuditRecord.kind == "tax-loss",
                    AuditRecord.id != (record_id or uuid.UUID(int=0)),
                    AuditRecord.body["origin_start"].astext == str(data.origin_start),
                )
                .limit(1)
            )
            if duplicate:
                raise HTTPException(
                    409, "Loss origin already registered for entity; use versioned correction"
                )
        if (
            kind == "foundation"
            and data.treatment == "APPROVED_TRANSPARENT"
            and not data.approval_evidence_id
        ):
            raise HTTPException(422, "FTA transparency approval evidence required")
        if kind == "related-party" and data.approved_adjustment_id:
            await record(db, ctx, eng.id, data.approved_adjustment_id, "adjustment", True)
        if kind == "group":
            if len({m.engagement_id for m in data.members}) != len(data.members):
                raise HTTPException(422, "Duplicate tax-group member")
            for member in data.members:
                await record(db, ctx, member.engagement_id, member.profile_id, "profile", True)
        if kind == "loss-transfer":
            await record(
                db, ctx, data.recipient_engagement_id, data.recipient_profile_id, "profile", True
            )
            if data.common_ownership < D("0.75") or not conditions_pass(
                data.conditions,
                {
                    "residence",
                    "alignment",
                    "not_exempt_or_qfzp",
                    "ownership_period",
                    "transfer_eligibility",
                },
            ):
                raise HTTPException(422, "Loss transfer statutory conditions incomplete")
    if kind in {"computation", "return"}:
        result = await run(db, ctx, eng.id, data.tax_run_id)
        if result.kind not in {"corporate-tax", "tax-group"}:
            raise HTTPException(422, "Tax computation run required")
        if kind == "return":
            if data.filing_state in {"FILED_EXTERNALLY", "ACKNOWLEDGED"}:
                if not data.filing_evidence_id or not data.external_reference.strip():
                    raise HTTPException(
                        422, "External filing requires evidence and genuine recorded reference"
                    )
                await evidence(db, ctx, eng.id, data.filing_evidence_id)
            if data.filing_state == "ACKNOWLEDGED":
                if not data.acknowledgement_evidence_id:
                    raise HTTPException(422, "Acknowledgement evidence required")
                await evidence(db, ctx, eng.id, data.acknowledgement_evidence_id)
    return data.model_dump(mode="json")


def conditions_pass(conditions, required=()):
    rows = {r.requirement: r for r in conditions}
    return (
        len(rows) == len(conditions)
        and set(required) <= set(rows)
        and all(
            r.assessment in {"PASS", "NOT_APPLICABLE"}
            and (r.assessment != "PASS" or r.evidence_record_ids)
            for r in rows.values()
        )
        and all(rows[k].assessment == "PASS" for k in required)
    )


async def approved(db, ctx, eid, kind, profile_id):
    return (
        await db.scalars(
            select(AuditRecord)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.kind == "tax-" + kind,
                AuditRecord.status.in_(APPROVED),
                AuditRecord.body["profile_id"].astext == str(profile_id),
            )
            .order_by(AuditRecord.created_at)
        )
    ).all()


async def dependencies_current(db, ctx, eid, result):
    from app.modules.tax.contracts import current

    if not await current(db, ctx, eid, result.results):
        return False
    for dependency in result.dependencies:
        source = await db.scalar(
            select(AuditRecord).where(
                AuditRecord.tenant_id == ctx.tenant_id, AuditRecord.id == dependency["id"]
            )
        )
        if source and source.kind == "tp-judgment":
            from app.modules.tp import service as tp

            linked = await tp.get_run(
                db, ctx, source.engagement_id, uuid.UUID(source.body["run_id"])
            )
            if not await tp.current(db, ctx, source.engagement_id, linked):
                return False
    if result.kind == "corporate-tax":
        if (
            result.results.get("audit_statement_obligation", {}).get("contract")
            != calc.AUDIT_OBLIGATION_CONTRACT
        ):
            return False
        financial = await ifrs.run(db, ctx, eid, uuid.UUID(result.inputs["financial_run_id"]))
        if not await ifrs.current_dependencies(db, ctx, eid, financial):
            return False
        expected = {item["id"] for item in result.dependencies}
        live = (
            await db.scalars(
                select(AuditRecord.id).where(
                    AuditRecord.tenant_id == ctx.tenant_id,
                    AuditRecord.engagement_id == eid,
                    AuditRecord.kind.in_(
                        [
                            "tax-adjustment",
                            "tax-exemption",
                            "tax-credit",
                            "tax-interest",
                            "tax-sbr",
                            "tax-qfzp",
                            "tax-deadline",
                        ]
                    ),
                    AuditRecord.status.in_(APPROVED),
                    AuditRecord.body["profile_id"].astext == result.inputs["profile_id"],
                )
            )
        ).all()
        if any(str(identifier) not in expected for identifier in live):
            return False
    return await ifrs.current_dependencies(db, ctx, eid, result)


async def save_run(db, ctx, eid, kind, inputs, deps, results, record_id=None):
    from app.modules.tax.contracts import attach

    results = await attach(db, ctx, eid, "QFZP" if kind == "qfzp" else "CT", results, inputs, deps)
    values = serial({"inputs": inputs, "dependencies": deps, "results": results})
    digest = hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    obj = TaxRun(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=eid,
        record_id=record_id,
        kind=kind,
        inputs=values["inputs"],
        dependencies=values["dependencies"],
        results=values["results"],
        sha256=digest,
        accounting_profit=D(results.get("accounting_profit", "0")),
        taxable_income=D(results.get("taxable_income", "0")),
        current_tax=D(results.get("current_tax", "0")),
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    from app.modules.audit_log.service import record as event

    event(db, ctx, "tax.calculated", obj.id, "calculation", {"kind": kind, "sha256": digest})
    return audit.serialize(obj)


async def profile_inputs(db, ctx, eid, pid):
    obj = await record(db, ctx, eid, pid, "profile", True)
    profile = s.TaxProfile.model_validate(clean(obj.body))
    financial, deps = await financial_source(db, ctx, eid, profile.financial_run_id)
    deps.extend(await evidence_dependencies(db, ctx, eid, [obj]))
    rules = {}
    snapshots = {}
    for category, rid in profile.rules.items():
        rule, parsed = await applicable_rule(db, ctx, eid, rid, profile, category)
        rules[category] = parsed
        deps.append(ifrs.dependency(rule))
        if parsed.publication_evidence_id:
            deps.append(
                ifrs.dependency(await evidence(db, ctx, eid, parsed.publication_evidence_id))
            )
        snapshots[category] = {
            "id": str(rule.id),
            "version": rule.version,
            "body": rule.body,
            "source": SOURCES[parsed.source_id],
        }
    return obj, profile, financial, deps, rules, snapshots


async def evidence_dependencies(db, ctx, eid, objects):
    result = []

    def find(value):
        found = []
        if isinstance(value, dict):
            for key, item in value.items():
                if (key.endswith("evidence_id") or key.endswith("rule_id")) and item:
                    found.append(item)
                elif key in {"evidence_record_ids", "evidence_ids"}:
                    found += item
                elif key == "sources":
                    found += [x["id"] for x in item if x["kind"] == "record"]
                elif key == "group_adjustments":
                    continue  # Each member's sources are validated in the scoped group bridge.
                else:
                    found += find(item)
        elif isinstance(value, list):
            for item in value:
                found += find(item)
        return found

    for obj in objects:
        result.append(ifrs.dependency(obj))
        for rid in set(find(obj.body)):
            source = await evidence(db, ctx, eid, uuid.UUID(rid))
            result.append(ifrs.dependency(source))
    return result


async def loss_lots(db, ctx, eng, profile, exclude_run=None):
    rows = (
        await db.scalars(
            select(AuditRecord)
            .join(Engagement, Engagement.id == AuditRecord.engagement_id)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                Engagement.entity_id == eng.entity_id,
                AuditRecord.kind == "tax-loss",
                AuditRecord.status.in_(APPROVED),
            )
            .order_by(AuditRecord.body["origin_start"].astext, AuditRecord.id)
        )
    ).all()
    lots = []
    deps = []
    for obj in rows:
        await audit.engagement(db, ctx, obj.engagement_id, "tax.profile.read")
        body = s.Loss.model_validate(clean(obj.body))
        if (
            body.origin_end >= profile.tax_start
            or body.eligibility != "PASS"
            or body.excluded_pre_ct_or_exempt
            or not (
                body.ownership_continuity
                or body.same_or_similar_business
                or body.listed_or_natural_exception
            )
        ):
            continue
        conditions = [LossPosting.tenant_id == ctx.tenant_id, LossPosting.bucket_id == obj.id]
        if exclude_run:
            conditions.append(
                or_(LossPosting.period_id != eng.period_id, TaxRun.kind == "loss-transfer")
            )
        used = await db.scalar(
            select(func.coalesce(func.sum(LossPosting.amount_used), 0))
            .join(TaxRun, TaxRun.id == LossPosting.tax_run_id)
            .where(*conditions)
        )
        lots.append({"id": str(obj.id), "available": str(D(body.amount) - D(used))})
        deps.append(ifrs.dependency(obj))
    return lots, deps


async def current_release(db, ctx, eng):
    return await db.scalar(
        select(TaxRelease)
        .where(
            TaxRelease.tenant_id == ctx.tenant_id,
            TaxRelease.entity_id == eng.entity_id,
            TaxRelease.period_id == eng.period_id,
        )
        .with_for_update()
    )


async def compute(db, ctx, eid, pid):
    with localcontext() as precision:
        precision.prec = 64
        eng = await audit.engagement(db, ctx, eid, "tax.computation.prepare", True)
        obj, profile, financial, deps, rules, rule_snapshots = await profile_inputs(
            db, ctx, eid, pid
        )
        if profile.classification not in {
            "resident_juridical",
            "nonresident_juridical",
            "permanent_establishment",
            "free_zone",
            "qfzp",
        }:
            raise HTTPException(
                422,
                "Classification assessment is supported; final computation for this special taxpayer requires a separately validated methodology",
            )
        issues = []
        lines = []
        profit = D(financial.results["totals"]["profit"]) - D(
            financial.results.get("profit_categories", {}).get("tax", "0")
        )
        adjustments = await approved(db, ctx, eid, "adjustment", pid)
        exemptions = await approved(db, ctx, eid, "exemption", pid)
        net = ZERO
        data: Any
        for row in adjustments:
            data = s.Adjustment.model_validate(clean(row.body))
            legal, rule = await applicable_rule(db, ctx, eid, data.rule_id, profile, "adjustments")
            amount = calc.adjustment_amount(data, rule.parameters)
            net += amount
            deps.append(ifrs.dependency(legal))
            lines.append(
                {
                    "id": str(row.id),
                    "label": row.reference,
                    "category": data.category,
                    "accounting_amount": data.accounting_amount,
                    "proposed_adjustment": data.proposed_adjustment,
                    "approved_adjustment": amount,
                    "source_accounts": data.account_codes,
                    "rule_id": str(legal.id),
                    "article": rule.article,
                    "evidence": data.evidence_record_ids,
                    "reviewers": row.body.get("review_approvers", []),
                    "status": row.status,
                }
            )
        exempt_source_codes: set[str] = set()
        for row in exemptions:
            data = s.Exemption.model_validate(clean(row.body))
            if exempt_source_codes.intersection(data.source_line_codes):
                raise HTTPException(
                    422, "Overlapping exempt income sources require a single reconciled schedule"
                )
            exempt_source_codes.update(data.source_line_codes)
            required = {
                "domestic_dividend": {"uae_resident_payer", "distribution_character"},
                "participation": {
                    "ownership",
                    "holding_period",
                    "subject_to_tax",
                    "profit_net_asset_rights",
                    "asset_composition",
                    "anti_abuse",
                },
                "foreign_pe": {"election", "foreign_tax_status", "prior_loss_recapture"},
            }.get(data.exemption_type, {"statutory_eligibility", "election"})
            if not conditions_pass(data.conditions, required):
                issues.append("Exemption conditions unresolved: " + row.reference)
            source_lines = {r["line_code"]: r for r in financial.results["lines"]}
            if any(code not in source_lines for code in data.source_line_codes):
                raise HTTPException(422, "Exemption source line outside financial statements")
            if data.amount > sum(
                (abs(D(source_lines[code]["current"])) for code in set(data.source_line_codes)),
                ZERO,
            ):
                raise HTTPException(422, "Exemption exceeds selected source line amounts")
            legal, _ = await applicable_rule(db, ctx, eid, data.rule_id, profile, "exemption")
            deps.append(ifrs.dependency(legal))
            net -= data.amount
            lines.append(
                {
                    "id": str(row.id),
                    "label": row.reference,
                    "category": "exempt_income",
                    "approved_adjustment": -data.amount,
                    "source_line_codes": data.source_line_codes,
                    "rule_id": str(legal.id),
                    "status": row.status,
                }
            )
        deps += await evidence_dependencies(db, ctx, eid, adjustments + exemptions + [obj])
        pre_interest = profit + net
        interest_rows = await approved(db, ctx, eid, "interest", pid)
        interest_result = None
        if len(interest_rows) > 1:
            issues.append("Multiple approved interest schedules")
        if interest_rows:
            if "interest" not in rules:
                raise HTTPException(409, "Approved interest rule required")
            data = s.Interest.model_validate(clean(interest_rows[0].body))
            if data.taxable_before_gidlr_losses != pre_interest:
                issues.append(
                    "Interest statutory EBITDA bridge differs from accounting-to-tax reconciliation"
                )
            interest_result = calc.interest(data, rules["interest"].parameters)
            net += D(interest_result["tax_adjustment"])
            lines.append(
                {
                    "label": "Interest restriction / carryforward",
                    "approved_adjustment": interest_result["tax_adjustment"],
                    "rule_id": str(profile.rules["interest"]),
                    "source_record_id": str(interest_rows[0].id),
                }
            )
            deps += await evidence_dependencies(db, ctx, eid, interest_rows)
        before_loss = profit + net
        release = await current_release(db, ctx, eng)
        lots, loss_deps = await loss_lots(
            db, ctx, eng, profile, release.tax_run_id if release else None
        )
        allocations = calc.loss_allocation(
            before_loss, rules["losses"].parameters.loss_percentage, lots
        )
        used = sum((D(x["used"]) for x in allocations), ZERO)
        deps += loss_deps
        taxable = max(ZERO, before_loss - used)
        current = calc.standard_tax(taxable, rules["standard"].parameters)
        sbr_rows = await approved(db, ctx, eid, "sbr", pid)
        sbr_result = None
        if len(sbr_rows) > 1:
            issues.append("Multiple approved SBR elections")
        if sbr_rows:
            if "sbr" not in rules:
                raise HTTPException(409, "Applicable approved SBR rule required")
            sbr_result = calc.small_business(
                s.SBR.model_validate(clean(sbr_rows[0].body)), profile, rules["sbr"].parameters
            )
            deps += await evidence_dependencies(db, ctx, eid, sbr_rows)
            if sbr_result["eligible_and_elected"]:
                taxable = ZERO
                current = ZERO
                used = ZERO
                allocations = []  # SBR periods do not generate or utilize tax losses/GIDLR carryforwards.
                if interest_result:
                    interest_result = {
                        "not_applicable_due_to_sbr": True,
                        "new_carryforward": "0",
                        "scope": "SBR period cannot create or utilize GIDLR carryforwards; prior balances preserved outside this period",
                    }
            else:
                issues.append("SBR election has failed eligibility conditions; withdraw or resolve")
        qfzp_result = None
        if profile.classification == "qfzp":
            rows = await approved(db, ctx, eid, "qfzp", pid)
            if len(rows) != 1 or "qfzp" not in rules:
                issues.append("One approved QFZP assessment and rule required")
            else:
                qfzp_result = calc.qfzp(
                    s.QFZP.model_validate(clean(rows[0].body)), profile, rules["qfzp"].parameters
                )
                deps += await evidence_dependencies(db, ctx, eid, rows)
                if qfzp_result["assessment"] != "PASS":
                    issues.append("QFZP qualification is not established")
                elif (
                    D(qfzp_result["qualifying_profit_if_qualified"])
                    + D(qfzp_result["special_nonqualifying_profit"])
                    != before_loss
                ):
                    issues.append("QFZP profit segmentation does not reconcile to tax bridge")
                else:
                    current = D(qfzp_result["qfzp_tax_if_qualified"])
                if used:
                    issues.append(
                        "QFZP special-income loss allocation requires a separately validated treatment"
                    )
        elif profile.classification not in {
            "resident_juridical",
            "nonresident_juridical",
            "permanent_establishment",
            "free_zone",
            "natural_person",
        }:
            issues.append("Special taxpayer computation requires a separately validated treatment")
        if profile.pillar_two_in_scope:
            issues.append("Pillar Two top-up computation outside Phase6 scope")
        audit_obligation = calc.audit_statement_obligation(profile)
        issues.extend(audit_obligation["issues"])
        entity = await db.get(LegalEntity, eng.entity_id)
        due = calc.filing_deadline(profile.tax_end, rules["deadline"].parameters.filing_months)
        gross_tax = current
        credit_rows = await approved(db, ctx, eid, "credit", pid)
        credit_total = ZERO
        credited_source_codes: set[str] = set()
        for credit_row in credit_rows:
            credit = s.ForeignTaxCredit.model_validate(clean(credit_row.body))
            if credited_source_codes.intersection(credit.source_line_codes):
                raise HTTPException(
                    422, "Overlapping foreign credits require separate financial sources"
                )
            credited_source_codes.update(credit.source_line_codes)
            legal, _ = await applicable_rule(db, ctx, eid, credit.rule_id, profile, "exemption")
            source_lines = {r["line_code"]: r for r in financial.results["lines"]}
            if any(code not in source_lines for code in credit.source_line_codes):
                raise HTTPException(422, "Foreign tax credit source outside financial package")
            exempt_codes = {code for row in exemptions for code in row.body["source_line_codes"]}
            if exempt_codes.intersection(credit.source_line_codes):
                raise HTTPException(
                    422, "Separate exempt and taxable foreign income sources before claiming credit"
                )
            credit_total += min(credit.foreign_tax_paid, credit.uae_tax_attributable)
            deps.append(ifrs.dependency(legal))
        foreign_credit = min(current, credit_total)
        current -= foreign_credit
        deps += await evidence_dependencies(db, ctx, eid, credit_rows)
        overrides = await approved(db, ctx, eid, "deadline", pid)
        for deadline_type in ["filing", "payment"]:
            choices = [r for r in overrides if r.body["deadline_type"] == deadline_type]
            if len(choices) > 1:
                issues.append("Multiple approved " + deadline_type + " deadline overrides")
        filing_override = next(
            (r.body["assessed_due_date"] for r in overrides if r.body["deadline_type"] == "filing"),
            str(due),
        )
        payment_override = next(
            (
                r.body["assessed_due_date"]
                for r in overrides
                if r.body["deadline_type"] == "payment"
            ),
            str(due),
        )
        deps += await evidence_dependencies(db, ctx, eid, overrides)
        result = {
            "entity": entity.name,
            "entity_id": str(entity.id),
            "period_start": str(profile.tax_start),
            "period_end": str(profile.tax_end),
            "currency": "AED",
            "accounting_profit": profit,
            "net_adjustments": net,
            "before_loss": before_loss,
            "loss_utilised": used,
            "loss_allocations": allocations,
            "current_tax_loss": ZERO
            if sbr_result and sbr_result["eligible_and_elected"]
            else max(ZERO, -before_loss),
            "taxable_income": taxable,
            "current_tax": current,
            "gross_tax": gross_tax,
            "foreign_tax_credit": foreign_credit,
            "unused_foreign_credit_no_carryforward": credit_total - foreign_credit,
            "lines": lines,
            "interest": interest_result,
            "sbr": sbr_result,
            "qfzp": qfzp_result,
            "audit_statement_obligation": audit_obligation,
            "rules": rule_snapshots,
            "financial_run_id": str(financial.id),
            "financial_sha256": financial.sha256,
            "filing_deadline": filing_override,
            "payment_deadline": payment_override,
            "exceptions": issues,
            "validation": {
                "ready": not issues,
                "checks": [{"code": "no_unresolved_tax_exceptions", "passed": not issues}],
            },
            "scope": "Approved facts and sourced rule versions; preparation only, no FTA filing or legal certification",
        }
        return await save_run(
            db,
            ctx,
            eid,
            "corporate-tax",
            {
                "profile_id": str(pid),
                "rules": rule_snapshots,
                "financial_run_id": str(financial.id),
            },
            deps,
            result,
            obj.id,
        )


async def calculate_record(db, ctx, eid, rid):
    await audit.engagement(db, ctx, eid, "tax.computation.prepare", True)
    obj = await record(db, ctx, eid, rid, approved=True)
    kind = obj.kind.removeprefix("tax-")
    data: Any = s.BODIES[kind].model_validate(clean(obj.body))
    _, profile, financial, deps, rules, snapshots = await profile_inputs(
        db, ctx, eid, data.profile_id
    )
    deps += await evidence_dependencies(db, ctx, eid, [obj])
    if kind == "interest":
        if "interest" not in rules:
            raise HTTPException(409, "Interest rule required")
        result = calc.interest(data, rules["interest"].parameters)
    elif kind == "qfzp":
        if "qfzp" not in rules:
            raise HTTPException(409, "QFZP rule required")
        result = calc.qfzp(data, profile, rules["qfzp"].parameters)
    elif kind == "sbr":
        if "sbr" not in rules:
            raise HTTPException(409, "SBR rule required")
        result = calc.small_business(data, profile, rules["sbr"].parameters)
    elif kind == "restructuring":
        threshold = D("0.75") if data.relief_type == "qualifying_group" else ZERO
        valid = (
            conditions_pass(
                data.conditions,
                {
                    "residence",
                    "alignment",
                    "not_exempt_or_qfzp",
                    "commercial_reason",
                    "statutory_transfer_conditions",
                },
            )
            and data.election_made
            and data.common_ownership >= threshold
        )
        end = date(
            data.transaction_date.year + 2,
            data.transaction_date.month,
            min(
                data.transaction_date.day,
                monthrange(data.transaction_date.year + 2, data.transaction_date.month)[1],
            ),
        )
        result = {
            "eligible_assessed": valid,
            "clawback_monitor_until": str(end),
            "potential_clawback": bool(
                data.clawback_event_date and data.clawback_event_date <= end
            ),
            "unrealised_difference": data.accounting_value - data.tax_value,
            "scope": "Human statutory eligibility review; no automatic tax-neutral posting",
        }
    elif kind == "transitional":
        result = {
            "assessed_adjustment": data.assessed_adjustment,
            "election_evidence_id": str(data.election_evidence_id),
            "scope": "Manual professional methodology; no automatic tax-base step-up or valuation",
        }
    elif kind == "foundation":
        result = {
            "treatment": data.treatment,
            "conditions_complete": conditions_pass(data.conditions),
            "scope": "Application/evidence assessment only; no automatic transparency",
        }
    elif kind == "group":
        return await group(db, ctx, eid, obj, data, profile, deps, rules, snapshots)
    else:
        raise HTTPException(422, "This record has no standalone calculation")
    result.update(
        {
            "currency": "AED",
            "period_start": str(profile.tax_start),
            "period_end": str(profile.tax_end),
            "rules": snapshots,
        }
    )
    return await save_run(db, ctx, eid, kind, obj.body, deps, result, obj.id)


async def group(db, ctx, eid, obj, data, profile, deps, rules, snapshots):
    if "group" not in rules:
        raise HTTPException(409, "Tax Group rule required")
    if not data.no_restricted_pre_group_attributes or not conditions_pass(
        data.conditions,
        {"fta_approval", "financial_alignment", "accounting_alignment", "group_boundary"},
    ):
        raise HTTPException(409, "Tax Group eligibility/pre-group attributes unresolved")
    amounts = []
    member_accounts = {}
    member_entities = set()
    if eid not in {member.engagement_id for member in data.members}:
        raise HTTPException(422, "Parent engagement must be included in its Tax Group")
    income = ZERO
    with localcontext() as precision:
        precision.prec = 64
        for member in sorted(data.members, key=lambda m: str(m.engagement_id)):
            _, p, financial, member_deps, _, _ = await profile_inputs(
                db, ctx, member.engagement_id, member.profile_id
            )
            if financial.results["entity_id"] in member_entities:
                raise HTTPException(422, "Same legal entity cannot be counted twice")
            member_entities.add(financial.results["entity_id"])
            member_accounts[member.engagement_id] = {
                r["code"]: D(r["adjusted"]) for r in financial.results["adjusted_trial_balance"]
            }
            if (
                min(member.share_capital, member.voting_rights, member.profit_net_asset_rights)
                < rules["group"].parameters.group_ownership
                or not member.resident_juridical
                or member.exempt_or_qfzp
                or p.classification != "resident_juridical"
            ):
                raise HTTPException(
                    422, "Tax Group member ownership/residence/exclusion conditions fail"
                )
            if (
                (p.tax_start, p.tax_end, p.accounting_framework)
                != (profile.tax_start, profile.tax_end, profile.accounting_framework)
                or member.entry_date > profile.tax_start
                or member.exit_date
                and member.exit_date < profile.tax_end
            ):
                raise HTTPException(
                    422,
                    "Partial-period entry/exit or misalignment requires a separate validated group package",
                )
            value = D(financial.results["totals"]["profit"]) - D(
                financial.results.get("profit_categories", {}).get("tax", "0")
            )
            # Member adjustments/exemptions must be incorporated in an explicit group bridge, not silently summed post-tax liabilities.
            income += value
            amounts.append(
                {
                    "engagement_id": str(member.engagement_id),
                    "profile_id": str(member.profile_id),
                    "accounting_profit": str(value),
                    "financial_run_id": str(financial.id),
                }
            )
            deps += member_deps
        net = ZERO
        for adjustment in data.group_adjustments:
            if adjustment.profile_id != data.profile_id:
                raise HTTPException(422, "Group adjustment profile mismatch")
            legal, rule = await applicable_rule(
                db, ctx, eid, adjustment.rule_id, profile, "adjustments"
            )
            source_eid = adjustment.source_engagement_id or eid
            accounts = member_accounts.get(source_eid, {})
            if any(code not in accounts for code in adjustment.account_codes) or abs(
                adjustment.accounting_amount
            ) > sum((abs(accounts[code]) for code in set(adjustment.account_codes)), ZERO):
                raise HTTPException(
                    422, "Group adjustment does not reconcile to member source accounts"
                )
            for rid in adjustment.evidence_record_ids:
                deps.append(ifrs.dependency(await evidence(db, ctx, source_eid, rid)))
            net += calc.adjustment_amount(adjustment, rule.parameters)
            deps.append(ifrs.dependency(legal))
        taxable = max(ZERO, income + net)
        result = {
            "entity": "Corporate Tax Group",
            "currency": "AED",
            "period_start": str(profile.tax_start),
            "period_end": str(profile.tax_end),
            "accounting_profit": income,
            "net_adjustments": net,
            "taxable_income": taxable,
            "current_tax": calc.standard_tax(taxable, rules["standard"].parameters),
            "members": amounts,
            "lines": [
                {
                    **r.model_dump(mode="json"),
                    "label": "Member " + str(r.source_engagement_id or eid) + " / " + r.category,
                    "approved_adjustment": r.proposed_adjustment,
                    "status": "APPROVED",
                }
                for r in data.group_adjustments
            ],
            "rules": snapshots,
            "loss_allocations": [],
            "exceptions": [],
            "validation": {
                "ready": True,
                "checks": [{"code": "scoped_group_eligibility", "passed": True}],
            },
            "scope": "Approved full-period Tax Group with no restricted pre-group attributes; explicit group bridge; not accounting consolidation; no Pillar Two",
        }
        return await save_run(db, ctx, eid, "tax-group", obj.body, deps, result, obj.id)


async def validate_action(db, ctx, eid, obj, action):
    kind = obj.kind.removeprefix("tax-")
    if (
        kind in {"rule", "loss", "loss-transfer", "computation", "return"}
        and obj.status in APPROVED
        and action in {"reopen", "return"}
    ):
        raise HTTPException(
            409,
            "Posted/legal source history cannot be reopened; create a new independently reviewed correction/version",
        )
    if action not in {"submit", "approve", "lock"}:
        return
    if kind in {"computation", "return"}:
        result = await run(db, ctx, eid, uuid.UUID(obj.body["tax_run_id"]))
        if not await dependencies_current(db, ctx, eid, result) or not result.results.get(
            "validation", {}
        ).get("ready"):
            raise HTTPException(
                409, "Tax inputs/rules changed or unresolved exceptions remain; regenerate"
            )
        if kind == "return":
            data = s.Return.model_validate(clean(obj.body))
            if not conditions_pass(
                data.checklist,
                {"taxpayer", "sources", "adjustments", "elections", "losses", "review_complete"},
            ):
                raise HTTPException(409, "Return preparation checklist incomplete")
            eng = await audit.engagement(db, ctx, eid, "tax.profile.read")
            released = await current_release(db, ctx, eng)
            if not released or released.tax_run_id != result.id:
                raise HTTPException(409, "Return requires the currently approved tax computation")


async def after_action(db, ctx, eid, obj, action):
    if action != "approve" or obj.status != "APPROVED":
        return
    if obj.kind == "tax-computation":
        result = await run(db, ctx, eid, uuid.UUID(obj.body["tax_run_id"]))
        eng = await audit.engagement(db, ctx, eid, "tax.profile.read")
        # Entity row serializes all loss allocations across periods and engagements.
        await db.scalar(
            select(LegalEntity)
            .where(LegalEntity.id == eng.entity_id, LegalEntity.tenant_id == ctx.tenant_id)
            .with_for_update()
        )
        previous = await current_release(db, ctx, eng)
        profile_obj = (
            await record(db, ctx, eid, uuid.UUID(result.inputs["profile_id"]), "profile", True)
            if result.kind == "corporate-tax"
            else None
        )
        if profile_obj:
            profile = s.TaxProfile.model_validate(clean(profile_obj.body))
            lots, _ = await loss_lots(
                db, ctx, eng, profile, previous.tax_run_id if previous else None
            )
            availability = {r["id"]: D(r["available"]) for r in lots}
            for allocation in result.results["loss_allocations"]:
                if D(allocation["used"]) > availability.get(allocation["loss_id"], ZERO):
                    raise HTTPException(
                        409, "Tax loss already utilized by another approved computation; regenerate"
                    )
        if previous:
            if previous.tax_run_id == result.id:
                raise HTTPException(409, "This immutable tax run is already approved")
            rows = (
                await db.execute(
                    select(LossPosting.bucket_id, func.sum(LossPosting.amount_used))
                    .join(TaxRun, TaxRun.id == LossPosting.tax_run_id)
                    .where(
                        LossPosting.tenant_id == ctx.tenant_id,
                        LossPosting.entity_id == eng.entity_id,
                        LossPosting.period_id == eng.period_id,
                        TaxRun.kind.in_({"corporate-tax", "tax-group"}),
                    )
                    .group_by(LossPosting.bucket_id)
                )
            ).all()
            for bucket, amount in rows:
                if amount:
                    db.add(
                        LossPosting(
                            tenant_id=ctx.tenant_id,
                            created_by=ctx.user_id,
                            entity_id=eng.entity_id,
                            period_id=eng.period_id,
                            bucket_id=bucket,
                            tax_run_id=result.id,
                            amount_used=-amount,
                            reason="Superseded approval reversal",
                        )
                    )
        for allocation in result.results.get("loss_allocations", []):
            if D(allocation["used"]):
                db.add(
                    LossPosting(
                        tenant_id=ctx.tenant_id,
                        created_by=ctx.user_id,
                        entity_id=eng.entity_id,
                        period_id=eng.period_id,
                        bucket_id=uuid.UUID(allocation["loss_id"]),
                        tax_run_id=result.id,
                        amount_used=D(allocation["used"]),
                        reason="Professionally approved loss utilization",
                    )
                )
        if previous:
            previous.tax_run_id = result.id
            previous.approval_id = obj.id
        else:
            db.add(
                TaxRelease(
                    tenant_id=ctx.tenant_id,
                    created_by=ctx.user_id,
                    entity_id=eng.entity_id,
                    period_id=eng.period_id,
                    tax_run_id=result.id,
                    approval_id=obj.id,
                )
            )
        await db.flush()


async def post_transfer(db, ctx, eid, rid):
    eng = await audit.engagement(db, ctx, eid, "tax.losses.manage", True)
    transfer = await record(db, ctx, eid, rid, "loss-transfer", True)
    data = s.LossTransfer.model_validate(clean(transfer.body))
    recipient = await audit.engagement(
        db, ctx, data.recipient_engagement_id, "tax.losses.manage", True
    )
    if eng.entity_id == recipient.entity_id:
        raise HTTPException(422, "Loss transfer requires distinct entities")
    for entity_id in sorted([eng.entity_id, recipient.entity_id], key=str):
        await db.scalar(
            select(LegalEntity)
            .where(LegalEntity.tenant_id == ctx.tenant_id, LegalEntity.id == entity_id)
            .with_for_update()
        )
    existing = await db.scalar(
        select(TaxRun.id).where(
            TaxRun.tenant_id == ctx.tenant_id,
            TaxRun.record_id == rid,
            TaxRun.kind == "loss-transfer",
        )
    )
    if existing:
        raise HTTPException(409, "This approved loss transfer is already posted")
    p = await record(db, ctx, eid, data.profile_id, "profile", True)
    receiver = await record(db, ctx, recipient.id, data.recipient_profile_id, "profile", True)
    source_profile = s.TaxProfile.model_validate(clean(p.body))
    target_profile = s.TaxProfile.model_validate(clean(receiver.body))
    if (
        source_profile.classification != "resident_juridical"
        or target_profile.classification != "resident_juridical"
        or (source_profile.tax_start, source_profile.tax_end, source_profile.accounting_framework)
        != (target_profile.tax_start, target_profile.tax_end, target_profile.accounting_framework)
    ):
        raise HTTPException(422, "Loss transfer residence/period/accounting conditions fail")
    source_release = await current_release(db, ctx, eng)
    if not source_release:
        raise HTTPException(409, "Approve donor's own loss utilization before transfer")
    await record(db, ctx, eid, source_release.approval_id, "computation", True)
    donor_run = await run(db, ctx, eid, source_release.tax_run_id)
    if not await dependencies_current(db, ctx, eid, donor_run):
        raise HTTPException(409, "Donor computation sources changed; reapprove before transfer")
    lots, _ = await loss_lots(db, ctx, eng, source_profile)
    source = next((x for x in lots if x["id"] == str(data.loss_id)), None)
    if not source or D(source["available"]) < data.amount:
        raise HTTPException(409, "Loss transfer exceeds unutilized eligible source balance")
    bucket = await db.scalar(
        select(AuditRecord).where(
            AuditRecord.tenant_id == ctx.tenant_id, AuditRecord.id == data.loss_id
        )
    )
    if not bucket:
        raise HTTPException(404, "Loss bucket not found")
    original = s.Loss.model_validate(clean(bucket.body))
    deps = [ifrs.dependency(x) for x in [transfer, p, receiver, bucket]]
    saved = await save_run(
        db,
        ctx,
        eid,
        "loss-transfer",
        transfer.body,
        deps,
        {
            "entity": "Reviewed loss transfer",
            "currency": "AED",
            "period_start": str(source_profile.tax_start),
            "period_end": str(source_profile.tax_end),
            "transferred_loss": data.amount,
            "recipient_entity_id": str(recipient.entity_id),
            "scope": "Posted approved prior-period loss transfer; recipient utilization separately capped",
        },
        transfer.id,
    )
    recipient_body = original.model_dump(mode="json")
    recipient_body.update(
        profile_id=str(receiver.id),
        amount=str(data.amount),
        origin_tax_run_id=None,
        transfer_source_id=str(transfer.id),
        source_reference="Approved loss transfer " + str(transfer.id),
    )
    new_bucket = AuditRecord(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        prepared_by=transfer.prepared_by,
        engagement_id=recipient.id,
        kind="tax-loss",
        reference="TRANSFER-" + str(transfer.id),
        title="Transferred eligible tax loss",
        status="APPROVED",
        body=recipient_body,
    )
    db.add(new_bucket)
    await audit.revision(db, ctx, new_bucket, "tax-transfer", "tax.loss.transferred")
    db.add(
        LossPosting(
            tenant_id=ctx.tenant_id,
            created_by=ctx.user_id,
            entity_id=eng.entity_id,
            period_id=eng.period_id,
            bucket_id=bucket.id,
            tax_run_id=uuid.UUID(saved["id"]),
            amount_used=data.amount,
            reason="Approved transfer to " + str(recipient.entity_id),
        )
    )
    await db.flush()
    return {**saved, "recipient_loss_id": str(new_bucket.id)}
