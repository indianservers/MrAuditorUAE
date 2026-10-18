import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal as D
from decimal import localcontext
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, text

from app.db.models.platform import EntityRelationship, FinancialPeriod, LegalEntity
from app.modules.accounting.models import ImportBatch, JournalLine
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.models import AuditRecord, EvidenceVersion
from app.modules.demo.guard import DEMO_TENANT
from app.modules.ifrs import service as ifrs
from app.modules.ifrs.calculations import serial
from app.modules.tax.service import financial_source
from app.modules.tp import calculations as calc
from app.modules.tp import schemas as s
from app.modules.tp.catalogue import LOCAL_SECTIONS, MASTER_SECTIONS, SOURCES
from app.modules.tp.models import Observation, TPRun

APPROVED = {"APPROVED", "LOCKED"}


async def evidence(db, ctx, eid, rid):
    obj = await audit.get_record(db, ctx, eid, rid, "tp.read")
    if obj.status not in APPROVED:
        raise HTTPException(409, "Independently approved evidence/working paper required")
    if obj.kind == "evidence":
        latest = await db.scalar(
            select(EvidenceVersion)
            .where(EvidenceVersion.tenant_id == ctx.tenant_id, EvidenceVersion.record_id == obj.id)
            .order_by(EvidenceVersion.number.desc())
            .limit(1)
        )
        if not latest or latest.scan_status != "CLEAN":
            raise HTTPException(409, "Clean scanned evidence required")
    return obj


def clean(body):
    return {
        k: v
        for k, v in body.items()
        if k
        not in {
            "calculation",
            "review_stage",
            "review_cycle",
            "review_approvers",
            "client_document",
        }
    }


def dep(obj):
    return {
        "id": str(obj.id),
        "version": obj.version,
        "status": obj.status,
        "kind": obj.kind,
        "synthetic": obj.body.get("synthetic") is True
        or obj.body.get("license_type") == "synthetic",
    }


async def record(db, ctx, eid, rid, kind=None, approved=False):
    obj = await audit.get_record(db, ctx, eid, rid, "tp.read")
    if kind and obj.kind != "tp-" + kind or not obj.kind.startswith("tp-"):
        raise HTTPException(422, "Incorrect TP source type")
    if approved and obj.status not in APPROVED:
        raise HTTPException(409, "Approved TP source required")
    return obj


async def profile_inputs(db, ctx, eid, pid):
    obj = await record(db, ctx, eid, pid, "profile", True)
    p = s.Profile.model_validate(clean(obj.body))
    financial, deps = await financial_source(db, ctx, eid, p.financial_run_id)
    selected = {}
    deps += [dep(obj)]
    for category, rid in p.rules.items():
        rule = await record(db, ctx, eid, rid, "rule", True)
        parsed = s.Rule.model_validate(clean(rule.body))
        if (
            parsed.category != category
            or parsed.effective_from > p.tax_start
            or parsed.effective_to
            and parsed.effective_to < p.tax_end
            or parsed.known_from > p.legal_as_of
        ):
            raise HTTPException(
                409, "TP rule not applicable to period/category/legal knowledge date"
            )
        selected[category] = (rule, parsed)
        deps.append(dep(rule))
    return obj, p, financial, deps, selected


async def scoped_source(db, ctx, eid, rid, kind, pid, approved=True):
    obj = await record(db, ctx, eid, rid, kind, approved)
    if obj.body.get("profile_id") != str(pid):
        raise HTTPException(422, "TP source belongs to a different profile")
    return obj


async def selected(db, ctx, eid, kind, pid):
    return (
        await db.scalars(
            select(AuditRecord)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.kind == "tp-" + kind,
                AuditRecord.status.in_(APPROVED),
                AuditRecord.body["profile_id"].astext == str(pid),
            )
            .order_by(AuditRecord.id)
        )
    ).all()


async def source_lines(db, ctx, eng, ids):
    from app.modules.vat.service import journal_ids

    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Duplicate source journal line")
    rows = (
        await db.scalars(
            select(JournalLine)
            .join(ImportBatch, ImportBatch.id == JournalLine.batch_id)
            .where(
                JournalLine.tenant_id == ctx.tenant_id,
                JournalLine.entity_id == eng.entity_id,
                JournalLine.period_id == eng.period_id,
                journal_ids(ids),
                ImportBatch.status == "active",
            )
        )
    ).all()
    if len(rows) != len(ids):
        raise HTTPException(422, "Journal source missing, inactive or outside entity/period")
    return rows


def verify_transaction(data, rel, p, lines):
    if rel.body["decision"] == "CONNECTED" and data.connected_payment_or_benefit is None:
        raise HTTPException(
            422, "Explicit connected-person payment/benefit classification required"
        )
    if len(data.journal_line_ids) != len(set(data.journal_line_ids)):
        raise HTTPException(422, "Duplicate source journal line")
    if rel.body["decision"] not in {"RELATED", "CONNECTED"}:
        raise HTTPException(409, "Reviewed related/connected relationship required")
    with localcontext() as precision:
        precision.prec = 64
        if str(data.counterparty_id) not in {
            rel.body["from_party_id"],
            rel.body["to_party_id"],
        }:
            raise HTTPException(422, "Counterparty not a party to the relationship")
        if (
            not p.tax_start <= data.transaction_date <= p.tax_end
            or data.transaction_date < date.fromisoformat(rel.body["effective_from"])
            or rel.body.get("effective_to")
            and data.transaction_date > date.fromisoformat(rel.body["effective_to"])
        ):
            raise HTTPException(422, "Transaction outside relationship/financial interval")
        if len({row.journal_id for row in lines}) != len(lines):
            raise HTTPException(
                422, "Select one economic leg per journal; do not double-count both sides"
            )
        base = sum((row.base_debit - row.base_credit for row in lines), D(0))
        original = sum((row.debit - row.credit for row in lines), D(0))
        if (
            any(
                row.currency != data.source_currency
                or row.functional_currency != data.base_currency
                or row.exchange_rate != data.exchange_rate
                or row.posting_date != data.transaction_date
                for row in lines
            )
            or base != data.base_amount
            or original != data.source_amount
        ):
            raise HTTPException(
                422,
                "Transaction amounts/currencies/date/FX do not match original journal facts",
            )
        if data.base_currency != "AED":
            raise HTTPException(422, "UAE disclosure requires a reviewed AED source population")


async def validate_body(db, ctx, eng, kind, data, record_id=None):
    kind = kind.removeprefix("tp-")
    if kind == "rule":
        source = SOURCES.get(data.source_id)
        if (
            not source
            or data.article not in source["articles"]
            or data.known_from < date.fromisoformat(source["known_from"])
        ):
            raise HTTPException(422, "Unverified source/article/knowledge date")
        if data.effective_to and data.effective_to < data.effective_from:
            raise HTTPException(422, "Invalid rule interval")
        duplicate = await db.scalar(
            select(AuditRecord.id).where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eng.id,
                AuditRecord.kind == "tp-rule",
                AuditRecord.id != (record_id or uuid.UUID(int=0)),
                AuditRecord.body["rule_key"].astext == data.rule_key,
                AuditRecord.body["rule_version"].astext == str(data.rule_version),
            )
        )
        if duplicate:
            raise HTTPException(409, "Rule version already exists")
        binding = {
            "relationships": ("CT-LAW", "35"),
            "connected_person": ("CT-LAW", "36"),
            "documentation": ("MD97-2023", "2"),
            "disclosure": ("CTGTXR1", "16.1"),
            "connected_disclosure": ("CTGTXR1", "16.2"),
            "apa": ("CTGAPA1", "3"),
        }
        if data.category in binding and (data.source_id, data.article) != binding[data.category]:
            raise HTTPException(
                422, "Rule category must match its verified statutory/guidance source"
            )
        if data.category == "methodology" and data.source_id not in {"OECD2022", "CTGTP1"}:
            raise HTTPException(422, "TP methodology requires registered OECD or FTA guidance")
        if data.category in {"documentation", "disclosure", "connected_disclosure"}:
            expected_source = "MD97-2023" if data.category == "documentation" else "CTGTXR1"
            if data.source_id != expected_source or data.parameters != s.RuleParameters():
                raise HTTPException(
                    422,
                    "Threshold adoption requires the registered source and verified v1 parameters",
                )
        if (
            data.category == "apa"
            and data.parameters.apa_materiality != s.RuleParameters().apa_materiality
        ):
            raise HTTPException(
                422,
                "Use the verified APA materiality indicator; below-indicator cases need separate justification",
            )
    if kind == "profile":
        if data.legal_as_of > date.today():
            raise HTTPException(422, "Legal knowledge date cannot be in the future")
        if data.mne_member and data.uae_headquartered_non_mne_group:
            raise HTTPException(422, "Contradictory multinational/non-MNE facts")
        period = await db.get(FinancialPeriod, eng.period_id)
        if not period or data.tax_start != period.start_date or data.tax_end != period.end_date:
            raise HTTPException(422, "TP profile period must match the financial engagement")
        await financial_source(db, ctx, eng.id, data.financial_run_id)
        if not {"relationships", "documentation", "disclosure", "methodology"} <= data.rules.keys():
            raise HTTPException(
                422, "Approved relationship/documentation/disclosure/methodology adoptions required"
            )
        for category, rid in data.rules.items():
            obj = await record(db, ctx, eng.id, rid, "rule", True)
            rule = s.Rule.model_validate(clean(obj.body))
            if (
                category != rule.category
                or rule.known_from > data.legal_as_of
                or rule.effective_from > data.tax_start
                or rule.effective_to
                and rule.effective_to < data.tax_end
            ):
                raise HTTPException(422, "Rule not applicable to profile")
    if hasattr(data, "profile_id"):
        _, p, financial, _, rules = await profile_inputs(db, ctx, eng.id, data.profile_id)
        if kind == "party":
            if data.entity_id:
                entity = await db.scalar(
                    select(LegalEntity).where(
                        LegalEntity.tenant_id == ctx.tenant_id, LegalEntity.id == data.entity_id
                    )
                )
                if not entity:
                    raise HTTPException(422, "Entity outside tenant")
            if data.phase6_counterparty_id:
                cp = await audit.get_record(db, ctx, eng.id, data.phase6_counterparty_id, "tp.read")
                if cp.kind != "tax-related-party" or cp.status not in APPROVED:
                    raise HTTPException(422, "Approved Phase6 counterparty assessment required")
        if kind == "relationship":
            parties = [
                await scoped_source(db, ctx, eng.id, rid, "party", data.profile_id)
                for rid in [data.from_party_id, data.to_party_id]
            ]
            if data.rule_id != p.rules["relationships"]:
                raise HTTPException(422, "Selected relationship rule required")
            if data.decision == "CONNECTED":
                if (
                    data.related_party_applicable is None
                    or not data.connected_person_rule_id
                    or data.connected_person_rule_id != p.rules.get("connected_person")
                ):
                    raise HTTPException(
                        422, "Review Article 35 overlap and adopt a separate Article 36 rule"
                    )
                cp_rule = rules["connected_person"][1]
                if cp_rule.source_id != "CT-LAW" or cp_rule.article != "36":
                    raise HTTPException(422, "Connected-person classification requires Article 36")
            entity_ids = [x.body.get("entity_id") for x in parties]
            if data.relationship_type == "ownership" and all(entity_ids):
                if not data.entity_relationship_id:
                    relation = await db.scalar(
                        select(EntityRelationship).where(
                            EntityRelationship.tenant_id == ctx.tenant_id,
                            EntityRelationship.parent_id == uuid.UUID(entity_ids[0]),
                            EntityRelationship.child_id == uuid.UUID(entity_ids[1]),
                            EntityRelationship.effective_from == data.effective_from,
                            EntityRelationship.ownership_percent == data.ownership * 100,
                        )
                    )
                    if not relation:
                        relation = EntityRelationship(
                            tenant_id=ctx.tenant_id,
                            created_by=ctx.user_id,
                            parent_id=uuid.UUID(entity_ids[0]),
                            child_id=uuid.UUID(entity_ids[1]),
                            ownership_percent=data.ownership * 100,
                            effective_from=data.effective_from,
                            effective_to=data.effective_to,
                        )
                        db.add(relation)
                        await db.flush()
                    data.entity_relationship_id = relation.id
                relation = await db.scalar(
                    select(EntityRelationship).where(
                        EntityRelationship.tenant_id == ctx.tenant_id,
                        EntityRelationship.id == data.entity_relationship_id,
                    )
                )
                if (
                    not relation
                    or [str(relation.parent_id), str(relation.child_id)] != entity_ids
                    or relation.ownership_percent / 100 != data.ownership
                    or relation.effective_from != data.effective_from
                    or relation.effective_to != data.effective_to
                ):
                    raise HTTPException(
                        422, "Ownership must reference matching existing EntityRelationship facts"
                    )
        if kind in {"transaction", "loan", "guarantee"}:
            rel = await scoped_source(
                db, ctx, eng.id, data.relationship_id, "relationship", data.profile_id
            )
            if rel.body["decision"] not in {"RELATED", "CONNECTED"}:
                raise HTTPException(409, "Reviewed related/connected relationship required")
        if kind == "transaction":
            await db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"{ctx.tenant_id}:{eng.id}:{data.profile_id}:tp-transactions"},
            )
            lines = await source_lines(db, ctx, eng, data.journal_line_ids)
            verify_transaction(data, rel, p, lines)
            others = (
                await db.scalars(
                    select(AuditRecord).where(
                        AuditRecord.tenant_id == ctx.tenant_id,
                        AuditRecord.engagement_id == eng.id,
                        AuditRecord.kind == "tp-transaction",
                        AuditRecord.id != (record_id or uuid.UUID(int=0)),
                        AuditRecord.body["profile_id"].astext == str(data.profile_id),
                    )
                )
            ).all()
            for other in others:
                if other.body["economic_key"] == data.economic_key or set(
                    other.body["journal_line_ids"]
                ) & set(map(str, data.journal_line_ids)):
                    raise HTTPException(
                        409, "Economic transaction or journal leg already classified"
                    )
            other_ids = {
                uuid.UUID(rid) for other in others for rid in other.body["journal_line_ids"]
            }
            if other_ids:
                from app.modules.vat.service import journal_ids

                used_journal = await db.scalar(
                    select(JournalLine.id)
                    .where(
                        JournalLine.tenant_id == ctx.tenant_id,
                        JournalLine.entity_id == eng.entity_id,
                        JournalLine.period_id == eng.period_id,
                        journal_ids(list(other_ids)),
                        JournalLine.journal_id.in_({row.journal_id for row in lines}),
                    )
                    .limit(1)
                )
                if used_journal:
                    raise HTTPException(
                        409,
                        "Journal already represented; do not classify its opposite accounting leg",
                    )
        if kind == "method":
            await scoped_source(db, ctx, eng.id, data.far_id, "far", data.profile_id)
            await scoped_source(db, ctx, eng.id, data.tested_party_id, "party", data.profile_id)
            alternatives = {"CUP", "RPM", "COST_PLUS", "TNMM", "PROFIT_SPLIT", "OTHER"} - {
                data.method
            }
            if not alternatives <= data.rejected_alternatives.keys() or any(
                not str(v).strip() for v in data.rejected_alternatives.values()
            ):
                raise HTTPException(
                    422, "Document each rejected alternative; no automatic TNMM selection"
                )
        if kind == "dataset":
            if not data.authorized_use or data.valid_until < data.observation_date:
                raise HTTPException(422, "Authorized dated license/use evidence required")
            if data.observation_date > min(p.legal_as_of, date.today()):
                raise HTTPException(
                    422, "Comparable observations cannot postdate the analysis knowledge date"
                )
        if kind == "study":
            method = await scoped_source(db, ctx, eng.id, data.method_id, "method", data.profile_id)
            if method.body["pli"] != data.pli:
                raise HTTPException(422, "Study PLI must match the approved method")
            if data.purpose != "profitability" and (
                data.pli != "value" or method.body["method"] != "CUP"
            ):
                raise HTTPException(
                    422, "Specialist observed-price studies require an explicit CUP/value method"
                )
            for rid in data.dataset_ids:
                await licensed_dataset(db, ctx, eng.id, rid, data.profile_id)
            if data.selected_target is not None and not data.target_rationale.strip():
                raise HTTPException(422, "Explicit target point needs professional rationale")
        if kind == "screening":
            study = await scoped_source(db, ctx, eng.id, data.study_id, "study", data.profile_id)
            ids = [x.observation_id for x in data.decisions]
            if len(ids) != len(set(ids)):
                raise HTTPException(422, "Duplicate screening decision")
            observations = (
                await db.scalars(
                    select(Observation).where(
                        Observation.tenant_id == ctx.tenant_id,
                        Observation.engagement_id == eng.id,
                        Observation.id.in_(ids),
                        Observation.dataset_id.in_(
                            [uuid.UUID(x) for x in study.body["dataset_ids"]]
                        ),
                    )
                )
            ).all()
            if len(observations) != len(ids):
                raise HTTPException(422, "Observation outside study/tenant")
            for x in data.decisions:
                if x.financial_adjustment and not x.adjustment_basis.strip():
                    raise HTTPException(422, "Financial adjustments require explicit support")
        if kind == "far":
            await scoped_source(db, ctx, eng.id, data.party_id, "party", data.profile_id)
        if kind == "segmentation":
            calc.segmentation(data, financial.results)
        if kind == "loan":
            from datetime import timedelta

            if (
                not p.tax_start
                <= (data.accrual_start or data.drawdown_date)
                < data.calculation_end
                <= p.tax_end + timedelta(days=1)
            ):
                raise HTTPException(
                    422,
                    "Select an accrual interval within the financial period; preserve earlier contract cashflow history",
                )
            for rid in [data.lender_id, data.borrower_id]:
                await scoped_source(db, ctx, eng.id, rid, "party", data.profile_id)
            if {str(data.lender_id), str(data.borrower_id)} != {
                rel.body["from_party_id"],
                rel.body["to_party_id"],
            }:
                raise HTTPException(422, "Loan counterparties differ from relationship")
            calc.loan_schedule(data)
        if kind in {"remuneration", "service", "royalty", "method"}:
            for rid in data.transaction_ids:
                await scoped_source(db, ctx, eng.id, rid, "transaction", data.profile_id)
        if kind == "service":
            rows = await source_lines(db, ctx, eng, data.cost_line_ids)
            if sum((x.base_debit - x.base_credit for x in rows), D(0)) != data.cost_pool:
                raise HTTPException(422, "Cost pool does not reconcile to actual journal costs")
            if len(data.recipients) != len(data.allocations) or set(map(str, data.recipients)) != {
                x.segment for x in data.allocations
            }:
                raise HTTPException(422, "Allocation recipients and approved parties must match")
            for rid in [data.provider_id, *data.recipients]:
                await scoped_source(db, ctx, eng.id, rid, "party", data.profile_id)
            calc.allocate(data.cost_pool, data.allocations)
        if (
            kind == "royalty"
            and not {"development", "enhancement", "maintenance", "protection", "exploitation"}
            <= data.dempe.keys()
        ):
            raise HTTPException(422, "All DEMPE functions need explicit review")
        if kind in {"localfile", "masterfile"}:
            keys = [x.key for x in data.sections]
            if len(keys) != len(set(keys)):
                raise HTTPException(422, "Duplicate document section")
            for section in data.sections:
                for rid in section.evidence_ids:
                    await evidence(db, ctx, eng.id, rid)
                for rid in section.run_ids:
                    await get_run(db, ctx, eng.id, rid)
            financial_reconciliation = await get_run(
                db, ctx, eng.id, data.financial_reconciliation_run_id
            )
            if financial_reconciliation.kind != "segmentation" or financial_reconciliation.inputs[
                "profile_id"
            ] != str(data.profile_id):
                raise HTTPException(422, "Same-profile segmentation reconciliation required")
            if data.consolidated_run_id:
                group = await ifrs.run(db, ctx, eng.id, data.consolidated_run_id)
                if group.kind != "consolidation" or not await ifrs.current_dependencies(
                    db, ctx, eng.id, group
                ):
                    raise HTTPException(409, "Current approved-source IFRS consolidation required")
        if kind == "judgment":
            run = await get_run(db, ctx, eng.id, data.run_id)

            def synthetic(value):
                if isinstance(value, dict):
                    return (
                        value.get("synthetic") is True
                        or value.get("software_test_data") is True
                        or any(synthetic(x) for x in value.values())
                    )
                return isinstance(value, list) and any(synthetic(x) for x in value)

            if (
                synthetic(run.results)
                or run.tenant_id == DEMO_TENANT
                or any(x.get("synthetic") for x in run.dependencies)
            ) and not data.software_test_only:
                raise HTTPException(
                    422,
                    "Synthetic benchmark judgments must be explicitly marked software test only",
                )
            if (
                run.inputs["profile_id"] != str(data.profile_id)
                or not data.no_automatic_percentile_conclusion
            ):
                raise HTTPException(
                    422, "Same-profile run and explicit professional judgment required"
                )
            if data.proposed_tax_adjustment < 0:
                if not data.fta_downward_approval_id:
                    raise HTTPException(422, "Downward tax adjustment needs FTA approval evidence")
                await evidence(db, ctx, eng.id, data.fta_downward_approval_id)
        if kind == "release":
            run = await get_run(db, ctx, eng.id, data.document_run_id)
            if (
                run.kind not in {"localfile", "masterfile"}
                or run.inputs["profile_id"] != str(data.profile_id)
                or not run.results.get("complete")
                or not data.confidential_notes_excluded
            ):
                raise HTTPException(
                    422, "Complete same-profile document and confidentiality review required"
                )
    for rid in getattr(data, "evidence_record_ids", []):
        await evidence(db, ctx, eng.id, rid)
    if hasattr(data, "profile_id"):
        await dependencies(db, ctx, eng.id, data)
    return data.model_dump(mode="json")


async def licensed_dataset(db, ctx, eid, rid, pid=None, export=False, ai=False):
    obj = await record(db, ctx, eid, rid, "dataset", True)
    body = s.Dataset.model_validate(clean(obj.body))
    profile = await record(db, ctx, eid, body.profile_id, "profile", True)
    if body.observation_date > min(date.fromisoformat(profile.body["legal_as_of"]), date.today()):
        raise HTTPException(409, "Dataset snapshot postdates the analysis knowledge date")
    if pid and body.profile_id != pid or not body.authorized_use or body.valid_until < date.today():
        raise HTTPException(409, "Dataset license missing/expired or wrong profile")
    if export and not body.allow_derived_export or ai and not body.allow_ai:
        raise HTTPException(403, "Dataset license does not permit this disclosure")
    return obj, body


async def get_run(db, ctx, eid, rid):
    await audit.engagement(db, ctx, eid, "tp.read")
    obj = await db.scalar(
        select(TPRun).where(
            TPRun.tenant_id == ctx.tenant_id, TPRun.engagement_id == eid, TPRun.id == rid
        )
    )
    if not obj:
        raise HTTPException(404, "TP run not found")
    return obj


async def record_graph(db, ctx, eid, refs, pid, parent=None, as_of=None, memo=None):
    """Scoped breadth-first snapshots, including the reviewed facts behind a method.

    Approval timestamps prevent a changed/reapproved child being silently treated
    as reviewed by its older parent. The cache lives only for one validation call.
    """
    state: dict[str, Any] = {} if memo is None else memo
    cache = state.setdefault("records", {})
    checked = state.setdefault("evidence_checked", set())
    queue = [(uuid.UUID(str(rid)), kind, parent) for rid, kind in refs]
    expanded: set[uuid.UUID] = set()
    output: dict[uuid.UUID, AuditRecord] = {}
    runs: set[tuple[str, Any]] = set()
    while queue:
        missing = {rid for rid, _, _ in queue if rid not in cache}
        if len(cache) + len(missing) > 10000:
            raise HTTPException(413, "TP source graph exceeds 10,000 records")
        if missing:
            rows = (
                await db.scalars(
                    select(AuditRecord).where(
                        AuditRecord.tenant_id == ctx.tenant_id,
                        AuditRecord.engagement_id == eid,
                        AuditRecord.id.in_(missing),
                    )
                )
            ).all()
            cache.update({row.id: row for row in rows})
        following = []
        for rid, expected, owner in queue:
            obj = cache.get(rid)
            if not obj:
                raise HTTPException(404, "TP source not found in this engagement")
            if expected and obj.kind != "tp-" + expected:
                raise HTTPException(422, "Incorrect TP source type")
            if obj.status not in APPROVED:
                raise HTTPException(409, "Approved transitive TP source required")
            if obj.kind.startswith("tp-"):
                if (
                    obj.kind == "tp-relationship"
                    and obj.body["decision"] == "CONNECTED"
                    and (
                        obj.body.get("related_party_applicable") is None
                        or not obj.body.get("connected_person_rule_id")
                    )
                ):
                    raise HTTPException(
                        409,
                        "Connected-person and related-party overlap require explicit reviewed classification",
                    )
                if obj.kind == "tp-profile":
                    matches = str(obj.id) == str(pid)
                else:
                    matches = obj.kind == "tp-rule" or obj.body.get("profile_id") == str(pid)
                if not matches:
                    raise HTTPException(422, "Linked TP fact belongs to different profile")
                if obj.kind == "tp-dataset":
                    license = s.Dataset.model_validate(clean(obj.body))
                    if not license.authorized_use or license.valid_until < date.today():
                        raise HTTPException(409, "Dataset authorization is missing or expired")
                    profile = cache.get(pid)
                    if not profile:
                        profile = await db.scalar(
                            select(AuditRecord).where(
                                AuditRecord.tenant_id == ctx.tenant_id,
                                AuditRecord.engagement_id == eid,
                                AuditRecord.id == pid,
                                AuditRecord.kind == "tp-profile",
                            )
                        )
                        cache[pid] = profile
                    if not profile or license.observation_date > min(
                        date.fromisoformat(profile.body["legal_as_of"]), date.today()
                    ):
                        raise HTTPException(
                            409, "Dataset snapshot postdates the analysis knowledge date"
                        )
            elif rid not in checked:
                await evidence(db, ctx, eid, rid)
                checked.add(rid)
            if owner is not None and obj.updated_at > owner.updated_at:
                raise HTTPException(
                    409,
                    "Underlying TP facts changed after parent review; return and review the parent",
                )
            if as_of is not None and obj.updated_at > as_of:
                raise HTTPException(409, "Underlying TP fact changed after calculation")
            output[rid] = obj
            if rid in expanded or not obj.kind.startswith("tp-"):
                continue
            expanded.add(rid)
            children, child_runs = references(clean(obj.body))
            following += [(uuid.UUID(str(child)), kind, obj) for child, kind in children]
            runs.update((str(child), obj.updated_at) for child in child_runs)
        queue = following
    # The normalized entity relationship is an independent source of ownership.
    relation_ids = {
        uuid.UUID(x.body["entity_relationship_id"])
        for x in output.values()
        if x.kind == "tp-relationship" and x.body.get("entity_relationship_id")
    }
    if relation_ids:
        relations = {
            x.id: x
            for x in (
                await db.scalars(
                    select(EntityRelationship).where(
                        EntityRelationship.tenant_id == ctx.tenant_id,
                        EntityRelationship.id.in_(relation_ids),
                    )
                )
            ).all()
        }
        for obj in output.values():
            if obj.kind != "tp-relationship" or not obj.body.get("entity_relationship_id"):
                continue
            core = relations.get(uuid.UUID(obj.body["entity_relationship_id"]))
            parties = [
                cache.get(uuid.UUID(obj.body[key])) for key in ["from_party_id", "to_party_id"]
            ]
            if (
                not core
                or any(x is None for x in parties)
                or [str(core.parent_id), str(core.child_id)]
                != [x.body.get("entity_id") for x in parties]
                or core.ownership_percent / 100 != D(obj.body["ownership"])
                or str(core.effective_from) != obj.body["effective_from"]
                or (str(core.effective_to) if core.effective_to else None)
                != obj.body.get("effective_to")
                or core.updated_at > obj.updated_at
            ):
                raise HTTPException(
                    409, "Normalized ownership source changed; review the TP relationship"
                )
    return list(output.values()), runs


async def current(db, ctx, eid, run, _memo=None):
    memo: dict[str, Any] = {} if _memo is None else _memo
    seen = memo.setdefault("runs", {})
    if run.id in seen:
        return seen[run.id]
    seen[run.id] = False
    profiles = memo.setdefault("profiles", set())
    pid = uuid.UUID(run.inputs["profile_id"])
    if pid not in profiles:
        try:
            _, _, financial, _, _ = await profile_inputs(db, ctx, eid, pid)
        except HTTPException:
            return False
        profiles.add(pid)
        memo.setdefault("ifrs", set()).add(financial.id)
    refs = [(x["id"], None) for x in run.dependencies if x.get("type") not in {"run", "ifrs_run"}]
    try:
        sources, implicit_runs = await record_graph(
            db, ctx, eid, refs, pid, as_of=run.created_at, memo=memo
        )
    except HTTPException:
        return False
    source_map = {str(x.id): x for x in sources}
    for item in run.dependencies:
        if item.get("type") == "ifrs_run":
            rid = uuid.UUID(item["id"])
            if rid not in memo.setdefault("ifrs", set()):
                source = await ifrs.run(db, ctx, eid, rid)
                if not await ifrs.current_dependencies(db, ctx, eid, source):
                    return False
                memo["ifrs"].add(rid)
        elif item.get("type") == "run":
            nested = await get_run(db, ctx, eid, uuid.UUID(item["id"]))
            if not await current(db, ctx, eid, nested, memo):
                return False
        else:
            obj = source_map.get(item["id"])
            if not obj or obj.version != item["version"] or obj.status != item["status"]:
                return False
    for rid, reviewed_at in implicit_runs:
        nested = await get_run(db, ctx, eid, uuid.UUID(rid))
        if nested.created_at > reviewed_at or not await current(db, ctx, eid, nested, memo):
            return False
    for kind, ids in run.inputs.get("populations", {}).items():
        if {str(x.id) for x in await selected(db, ctx, eid, kind, run.inputs["profile_id"])} != set(
            ids
        ):
            return False
    if run.inputs.get("observation_ids") is not None:
        live = (
            await db.scalars(
                select(Observation.id).where(
                    Observation.tenant_id == ctx.tenant_id,
                    Observation.dataset_id.in_([uuid.UUID(x) for x in run.inputs["dataset_ids"]]),
                )
            )
        ).all()
        if set(map(str, live)) != set(run.inputs["observation_ids"]):
            return False
    seen[run.id] = True
    return True


async def save(db, ctx, eid, kind, p, inputs, deps, result, rid=None):
    value = serial({"inputs": inputs, "dependencies": deps, "results": result})
    digest = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    obj = TPRun(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=eid,
        record_id=rid,
        kind=kind,
        period_start=p.tax_start,
        period_end=p.tax_end,
        inputs=value["inputs"],
        dependencies=value["dependencies"],
        results=value["results"],
        sha256=digest,
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    from app.modules.audit_log.service import record as event

    event(db, ctx, "tp.calculated", obj.id, "tp", {"kind": kind, "sha256": digest})
    return obj


REFERENCE_KINDS = {
    "party_id": "party",
    "counterparty_id": "party",
    "from_party_id": "party",
    "to_party_id": "party",
    "provider_id": "party",
    "lender_id": "party",
    "borrower_id": "party",
    "tested_party_id": "party",
    "relationship_id": "relationship",
    "far_id": "far",
    "method_id": "method",
    "study_id": "study",
    "benchmark_study_id": "study",
    "credit_id": "credit",
}


def references(body):
    records = []
    runs = []
    if isinstance(body, dict):
        for key, value in body.items():
            if not value:
                continue
            if key in REFERENCE_KINDS or key in {
                "rule_id",
                "connected_person_rule_id",
                "phase6_counterparty_id",
                "fta_downward_approval_id",
            }:
                records.append((value, REFERENCE_KINDS.get(key)))
            elif key in {
                "evidence_record_ids",
                "evidence_ids",
                "dataset_ids",
                "transaction_ids",
                "recipients",
            }:
                records += [(x, None) for x in value]
            elif key in {
                "run_id",
                "benchmark_run_id",
                "financial_reconciliation_run_id",
                "document_run_id",
            }:
                runs.append(value)
            elif key == "run_ids":
                runs += value
            elif isinstance(value, (dict, list)):
                a, b = references(value)
                records += a
                runs += b
    elif isinstance(body, list):
        for value in body:
            a, b = references(value)
            records += a
            runs += b
    return records, runs


async def dependencies(db, ctx, eid, data, parent=None):
    records, runs = references(data.model_dump(mode="json"))
    result = []
    if getattr(data, "consolidated_run_id", None):
        source = await ifrs.run(db, ctx, eid, data.consolidated_run_id)
        result.append({"type": "ifrs_run", "id": str(source.id)})
    sources, nested_runs = await record_graph(
        db, ctx, eid, set(records), data.profile_id, parent=parent
    )
    result += [dep(obj) for obj in sources]
    run_ids = set(runs) | {rid for rid, _ in nested_runs}
    memo: dict[str, Any] = {}
    for rid in run_ids:
        run = await get_run(db, ctx, eid, uuid.UUID(rid))
        if (
            run.inputs["profile_id"] != str(data.profile_id)
            or parent is not None
            and run.created_at > parent.updated_at
            or any(run.created_at > at for source_id, at in nested_runs if source_id == rid)
            or not await current(db, ctx, eid, run, memo)
        ):
            raise HTTPException(409, "Current same-profile calculation required")
        result.append({"type": "run", "id": str(run.id), "sha256": run.sha256})
    return result


async def matrix(db, ctx, eid, pid):
    with localcontext() as precision:
        precision.prec = 64
        return await _matrix(db, ctx, eid, pid)


async def _matrix(db, ctx, eid, pid):
    eng = await audit.engagement(db, ctx, eid, "tp.calculate", True)
    _, p, financial, deps, rules = await profile_inputs(db, ctx, eid, pid)
    records = await selected(db, ctx, eid, "transaction", pid)
    relationships = await selected(db, ctx, eid, "relationship", pid)
    rels = {str(x.id): x for x in relationships}
    sources, _ = await record_graph(
        db, ctx, eid, [(str(x.id), "transaction") for x in records], pid
    )
    deps += [dep(x) for x in sources]
    source_map = {str(x.id): x for x in sources}
    typed = [(obj, s.Transaction.model_validate(clean(obj.body))) for obj in records]
    ids = {rid for _, data in typed for rid in data.journal_line_ids}
    journal_sources = {x.id: x for x in await source_lines(db, ctx, eng, list(ids))} if ids else {}
    lines = []
    consumed: set[str] = set()
    economic = set()
    journals: set[uuid.UUID] = set()
    for obj, data in typed:
        rel = rels.get(str(data.relationship_id))
        if not rel:
            raise HTTPException(409, "Approved relationship source missing")
        verify_transaction(data, rel, p, [journal_sources[rid] for rid in data.journal_line_ids])
        if data.source_role != "original":
            continue
        source_journals = {journal_sources[rid].journal_id for rid in data.journal_line_ids}
        if journals.intersection(source_journals):
            raise HTTPException(
                409, "Duplicate economic journal; both accounting sides cannot be counted"
            )
        journals.update(source_journals)
        if data.economic_key in economic or consumed.intersection(map(str, data.journal_line_ids)):
            raise HTTPException(409, "Duplicate economic source population")
        economic.add(data.economic_key)
        consumed.update(map(str, data.journal_line_ids))
        rel = rels.get(str(data.relationship_id))
        if not rel:
            raise HTTPException(409, "Approved relationship source missing")
        party = source_map[str(data.counterparty_id)]
        line = {
            "id": str(obj.id),
            **data.model_dump(mode="json"),
            "counterparty": party.body["name"],
            "country": party.body["jurisdiction"],
            "relationship_decision": rel.body["decision"],
            "rp_applicable": rel.body["decision"] == "RELATED"
            or rel.body.get("related_party_applicable") is True,
            "period_start": str(p.tax_start),
            "period_end": str(p.tax_end),
            "ledger_difference": "0",
            "review_status": obj.status,
        }
        lines.append(line)
        deps += [dep(obj), dep(rel), dep(party)]
    return await save(
        db,
        ctx,
        eid,
        "matrix",
        p,
        {
            "profile_id": str(pid),
            "populations": {
                "transaction": [str(x.id) for x in records],
                "relationship": [str(x.id) for x in relationships],
            },
        },
        deps,
        {
            "rows": lines,
            "reconciled": True,
            "amount_basis": "Signed economic GL legs; original transactions only; settlements/eliminations excluded",
            "base_currency": "AED",
            "software_test_data": ctx.tenant_id == DEMO_TENANT
            or any(x.get("synthetic") for x in deps),
            "total_gross_values": sum((abs(D(x["base_amount"])) for x in lines), D(0)),
        },
    )


async def calculate(db, ctx, eid, rid):
    eng = await audit.engagement(db, ctx, eid, "tp.calculate", True)
    obj = await record(db, ctx, eid, rid, approved=True)
    kind = obj.kind.removeprefix("tp-")
    if kind in {
        "rule",
        "profile",
        "party",
        "relationship",
        "transaction",
        "dataset",
        "screening",
        "judgment",
        "release",
    }:
        raise HTTPException(422, "Use the dedicated source, matrix or release workflow")
    data: Any = s.BODIES[kind].model_validate(clean(obj.body))
    profile, p, financial, deps, rules = await profile_inputs(db, ctx, eid, data.profile_id)
    deps += [dep(obj)] + await dependencies(db, ctx, eid, data, parent=obj)
    inputs: dict[str, Any] = {"profile_id": str(data.profile_id), "record_id": str(rid)}
    with localcontext() as precision:
        precision.prec = 64
        if kind == "segmentation":
            result = calc.segmentation(data, financial.results)
        elif kind == "study":
            observations = (
                await db.scalars(
                    select(Observation)
                    .where(
                        Observation.tenant_id == ctx.tenant_id,
                        Observation.engagement_id == eid,
                        Observation.dataset_id.in_(data.dataset_ids),
                    )
                    .order_by(Observation.company_key, Observation.fiscal_year)
                )
            ).all()
            if len(observations) > 50000:
                raise HTTPException(
                    422, "Study population exceeds 50,000 observations; partition the study"
                )
            screenings = await selected(db, ctx, eid, "screening", data.profile_id)
            screenings = [x for x in screenings if x.body["study_id"] == str(obj.id)]
            decisions = {}
            for screen in screenings:
                deps.append(dep(screen))
                for row in screen.body["decisions"]:
                    if row["observation_id"] in decisions:
                        raise HTTPException(
                            409, "Conflicting approved screening population; version the study"
                        )
                    decisions[row["observation_id"]] = row
            accepted = []
            seen = set()
            synthetic = False
            for dataset_id in data.dataset_ids:
                _, license = await licensed_dataset(db, ctx, eid, dataset_id, data.profile_id)
                synthetic |= license.license_type == "synthetic"
            for observation in observations:
                key = (observation.company_key, observation.fiscal_year)
                if key in seen:
                    raise HTTPException(
                        409, "Duplicate company/year across datasets; resolve explicitly"
                    )
                seen.add(key)
                decision = decisions.get(str(observation.id))
                if decision and decision["decision"] == "ACCEPT":
                    if synthetic and "synthetic" not in observation.name.lower():
                        raise HTTPException(422, "Synthetic comparable names must be explicit")
                    accepted.append(
                        {
                            **{
                                col.name: getattr(observation, col.name)
                                for col in observation.__table__.columns
                            },
                            "financial_adjustment": D(decision["financial_adjustment"]),
                        }
                    )
            result = calc.benchmark(accepted, data)
            result.update(
                {
                    "synthetic": synthetic,
                    "total_imported": len(observations),
                    "accepted": len(accepted),
                    "rejected": sum(x["decision"] == "REJECT" for x in decisions.values()),
                    "pending": sum(str(x.id) not in decisions for x in observations),
                    "dataset_ids": list(map(str, data.dataset_ids)),
                    "ready": bool(result["n"])
                    and all(str(x.id) in decisions for x in observations),
                    "purpose": data.purpose,
                    "pli": data.pli,
                    "currency": data.currency,
                    "conclusion": "SOFTWARE TEST POPULATION ONLY"
                    if synthetic
                    else "Professional economic review required",
                }
            )
            inputs.update(
                dataset_ids=list(map(str, data.dataset_ids)),
                observation_ids=list(map(lambda x: str(x.id), observations)),
                populations={
                    "screening": [
                        str(x.id)
                        for x in await selected(db, ctx, eid, "screening", data.profile_id)
                    ]
                },
            )
        elif kind == "loan":
            result = calc.loan_schedule(data)
            if data.benchmark_study_id:
                benchmark_run = await latest_record_run(
                    db, ctx, eid, data.benchmark_study_id, "study"
                )
                if (
                    benchmark_run.results["purpose"] != "interest"
                    or benchmark_run.results["currency"] != data.currency
                ):
                    raise HTTPException(422, "Interest benchmark currency/purpose mismatch")
                result["benchmark"] = {
                    key: benchmark_run.results.get(key)
                    for key in [
                        "lower_quartile",
                        "median",
                        "upper_quartile",
                        "synthetic",
                        "selected_target",
                        "ready",
                    ]
                }
                target = benchmark_run.results.get("selected_target")
                result["estimated_impact_at_selected_target"] = (
                    calc.q(
                        D(result["weighted_average_principal"])
                        * (data.annual_rate - D(target))
                        * calc.fraction(
                            data.accrual_start or data.drawdown_date,
                            data.calculation_end,
                            data.day_count,
                        )
                    )
                    if target is not None
                    else None
                )
                result["impact_scope"] = (
                    "Selected constant-rate simple exposure illustration; not a recomputed floating/compound schedule or automatic adjustment"
                )
                deps.append(
                    {"type": "run", "id": str(benchmark_run.id), "sha256": benchmark_run.sha256}
                )
        elif kind == "credit":
            result = {
                "net_debt": data.debt - data.cash,
                "interest_coverage": calc.ratio(data.ebit, data.interest),
                "liquidity": calc.ratio(data.current_assets, data.current_liabilities),
                "proxy_label": data.proxy_label,
                "methodology": data.proxy_methodology,
                "scope": "User-supported internal proxy assessment only; not a validated public credit rating",
            }
        elif kind == "remuneration":
            for transaction_id in data.transaction_ids:
                transaction = await scoped_source(
                    db, ctx, eid, transaction_id, "transaction", data.profile_id
                )
                relation = await scoped_source(
                    db,
                    ctx,
                    eid,
                    uuid.UUID(transaction.body["relationship_id"]),
                    "relationship",
                    data.profile_id,
                )
                if relation.body["decision"] != "CONNECTED" or transaction.body[
                    "counterparty_id"
                ] != str(data.party_id):
                    raise HTTPException(
                        422,
                        "Remuneration requires source transactions classified to this connected person",
                    )
            total = sum(
                (
                    getattr(data, key)
                    for key in ["base_salary", "bonus", "allowances", "benefits", "management_fees"]
                ),
                D(0),
            )
            amount = await transaction_total(db, ctx, eid, data.transaction_ids)
            result = {
                "total_compensation": total,
                "source_gl_value": amount,
                "difference": total - amount,
                "review_required": True,
                "comparability_adjustment": data.comparability_adjustment,
                "adjusted_comparison_amount": total + data.comparability_adjustment,
                "scope": "Percentile comparison does not establish excessive pay or deductibility",
            }
            if data.study_id:
                bench = await latest_record_run(db, ctx, eid, data.study_id, "study")
                if bench.results["purpose"] != "remuneration" or bench.results["currency"] != "AED":
                    raise HTTPException(422, "AED remuneration benchmark required")
                result["benchmark"] = {
                    key: bench.results.get(key)
                    for key in ["lower_quartile", "median", "upper_quartile", "synthetic", "ready"]
                }
                deps.append({"type": "run", "id": str(bench.id), "sha256": bench.sha256})
        elif kind == "service":
            await validate_body(db, ctx, eng, kind, data, obj.id)
            allocations = calc.allocate(data.cost_pool, data.allocations)
            for row in allocations:
                row["markup_amount"] = calc.q(row["amount"] * data.markup)
                row["charge"] = row["amount"] + row["markup_amount"]
            result = {
                "cost_pool": data.cost_pool,
                "allocations": allocations,
                "allocation_difference": data.cost_pool
                - sum((x["amount"] for x in allocations), D(0)),
                "total_charge": sum((x["charge"] for x in allocations), D(0)),
                "benefit_test": data.benefit_test,
                "markup": data.markup,
                "scope": "Approved supplied markup only; no generic 5 percent safe harbour assumption",
            }
        elif kind == "royalty":
            result = {
                "revenue_base": data.revenue_base,
                "rate": data.rate,
                "royalty": calc.q(data.revenue_base * data.rate),
                "dempe": data.dempe,
                "scope": "Reviewed supplied base/rate; no automatic economic ownership conclusion",
            }
        elif kind == "guarantee":
            result = {
                "fee": calc.q(
                    data.principal * data.selected_rate * D(data.days) / data.denominator
                ),
                "methodology": data.pricing_methodology,
                "benefit_assessment": data.benefit_assessment,
                "scope": "Reviewed simple selected fee only; no inferred guarantee benefit or market rate",
            }
        elif kind == "comparability":
            result = calc.working_capital(data)
        elif kind == "disclosure":
            source = await matrix(db, ctx, eid, data.profile_id)
            if any(x["relationship_decision"] == "CONNECTED" for x in source.results["rows"]):
                if (
                    "connected_disclosure" not in rules
                    or rules["connected_disclosure"][1].source_id != "CTGTXR1"
                    or rules["connected_disclosure"][1].article != "16.2"
                ):
                    raise HTTPException(
                        409, "Adopt FTA return guide section 16.2 for connected-person disclosure"
                    )
            revenue = -sum(
                (D(x["current"]) for x in financial.results["lines"] if x["section"] == "income"),
                D(0),
            )
            params = rules["disclosure"][1].parameters.model_copy(
                update={
                    "own_revenue": rules["documentation"][1].parameters.own_revenue,
                    "group_revenue": rules["documentation"][1].parameters.group_revenue,
                    "connected_total": rules.get("connected_disclosure", rules["disclosure"])[
                        1
                    ].parameters.connected_total,
                }
            )
            result = calc.disclosure(p, revenue, source.results["rows"], params)
            result["ready"] = data.population_complete
            deps.append({"type": "run", "id": str(source.id), "sha256": source.sha256})
        elif kind in {"localfile", "masterfile"}:
            required = set(LOCAL_SECTIONS if kind == "localfile" else MASTER_SECTIONS)
            missing = sorted(
                required
                - {x.key for x in data.sections if x.human_verified and x.narrative.strip()}
            )
            reconciliation = await get_run(db, ctx, eid, data.financial_reconciliation_run_id)
            summaries = []
            section_runs: dict[str, list[Any]] = {}
            for section in data.sections:
                section_runs[section.key] = []
                for source_id in section.run_ids:
                    source = await get_run(db, ctx, eid, source_id)
                    section_runs[section.key].append(source)
                    allowed = {
                        "n",
                        "minimum",
                        "maximum",
                        "mean",
                        "median",
                        "lower_quartile",
                        "upper_quartile",
                        "selected_target",
                        "pli",
                        "purpose",
                        "currency",
                        "synthetic",
                        "total_interest",
                        "translated_interest",
                        "principal_outstanding",
                        "weighted_average_principal",
                        "weighted_average_rate",
                        "cost_pool",
                        "total_charge",
                        "allocation_difference",
                        "total_compensation",
                        "source_gl_value",
                        "difference",
                        "royalty",
                        "fee",
                        "segments",
                        "total_gross_values",
                        "reconciled",
                    }
                    summaries.append(
                        {
                            "run_id": str(source.id),
                            "kind": source.kind,
                            "results": {
                                key: value
                                for key, value in source.results.items()
                                if key in allowed
                            },
                        }
                    )
            if kind == "localfile":
                by_key = {x.key: x for x in data.sections}
                for section_key, source_kind in [("far", "tp-far"), ("method", "tp-method")]:
                    if section_key in by_key:
                        evidence_records = [
                            await evidence(db, ctx, eid, x)
                            for x in by_key[section_key].evidence_ids
                        ]
                        if not any(x.kind == source_kind for x in evidence_records):
                            missing.append(section_key + " reviewed typed source")
                for section_key, source_kind in [
                    ("benchmarking", "study"),
                    ("controlled_transactions", "matrix"),
                ]:
                    if not any(
                        x.kind == source_kind
                        and x.results.get("ready", x.results.get("reconciled", False))
                        for x in section_runs.get(section_key, [])
                    ):
                        missing.append(section_key + " current completed calculation")
            result = {
                "document_type": kind,
                "sections": [x.model_dump(mode="json") for x in data.sections],
                "missing_sections": missing,
                "complete": not missing
                and data.checklist_complete
                and reconciliation.results["reconciled"],
                "annual_version": data.annual_version,
                "calculation_summaries": summaries,
                "synthetic": any(x["results"].get("synthetic") for x in summaries),
                "financial_source_id": str(financial.id),
                "source_profit": financial.results["totals"]["profit"],
                "financial_reconciliation_run_id": str(reconciliation.id),
                "scope": "Source-linked preparation; human verified checklist does not automatically certify all legal requirements",
            }
        elif kind == "apa":
            if "apa" not in rules:
                raise HTTPException(409, "Approved APA guidance adoption required")
            result = {
                "materiality_indicator_met": data.proposed_value
                >= rules["apa"][1].parameters.apa_materiality,
                "checklist_complete": all(data.checklist.values()),
                "critical_assumptions": data.critical_assumptions,
                "cross_border_commencement_verified": data.cross_border_commencement_verified,
                "status": data.status,
                "scope": "Readiness only; materiality is an indicator, not absolute acceptance; no submission or APA assurance",
            }
        elif kind in {"far", "method"}:
            result = {
                "reviewed_facts": data.model_dump(mode="json"),
                "human_review_required": True,
                "scope": "Documented professional assessment; no automated best-method assertion",
            }
        else:
            raise HTTPException(422, "Unsupported calculator")
        result = serial(
            {
                **result,
                "software_test_data": ctx.tenant_id == DEMO_TENANT
                or any(x.get("synthetic") for x in deps),
                "entity_id": str(eng.entity_id),
                "period_start": str(p.tax_start),
                "period_end": str(p.tax_end),
                "profile_id": str(data.profile_id),
                "rules": {
                    key: {
                        "rule_record_id": str(r.id),
                        "version": r.version,
                        "body": r.body,
                        "official_source": SOURCES[b.source_id],
                    }
                    for key, (r, b) in rules.items()
                },
            }
        )
    return await save(db, ctx, eid, kind, p, inputs, deps, result, obj.id)


async def transaction_total(db, ctx, eid, ids):
    result = D(0)
    for rid in ids:
        row = await record(db, ctx, eid, rid, "transaction", True)
        result += abs(D(row.body["base_amount"]))
    return result


async def latest_record_run(db, ctx, eid, rid, kind):
    run = await db.scalar(
        select(TPRun)
        .where(
            TPRun.tenant_id == ctx.tenant_id,
            TPRun.engagement_id == eid,
            TPRun.record_id == rid,
            TPRun.kind == kind,
        )
        .order_by(TPRun.created_at.desc(), TPRun.id)
        .limit(1)
    )
    if not run or not await current(db, ctx, eid, run) or not run.results.get("ready", True):
        raise HTTPException(409, "Current completed source calculation required")
    return run


async def validate_action(db, ctx, eid, obj, action):
    if (
        obj.status in APPROVED
        and action in {"return", "reopen"}
        and obj.kind
        in {
            "tp-rule",
            "tp-dataset",
            "tp-study",
            "tp-judgment",
            "tp-release",
            "tp-localfile",
            "tp-masterfile",
        }
    ):
        raise HTTPException(409, "Preserve approved history; create a new version")
    if action not in {"submit", "approve", "lock"}:
        return
    kind = obj.kind.removeprefix("tp-")
    if kind in s.BODIES and kind != "rule":
        data: Any = s.BODIES[kind].model_validate(clean(obj.body))
        eng = await audit.engagement(db, ctx, eid, "tp.read")
        await validate_body(db, ctx, eng, kind, data, obj.id)
        if hasattr(data, "profile_id"):
            await dependencies(
                db, ctx, eid, data, parent=obj if action in {"approve", "lock"} else None
            )
        if kind in {"localfile", "masterfile"}:
            required = set(LOCAL_SECTIONS if kind == "localfile" else MASTER_SECTIONS)
            if not data.checklist_complete or not required <= {
                x.key for x in data.sections if x.human_verified
            }:
                raise HTTPException(409, "Complete verified sections and checklist before review")
        if kind == "release":
            run = await get_run(db, ctx, eid, data.document_run_id)
            await export_allowed(db, ctx, eid, run)


async def export_allowed(db, ctx, eid, run):
    if not await current(db, ctx, eid, run):
        raise HTTPException(409, "Stale TP source population; recalculate and review")
    visited = set()

    async def check(source):
        if source.id in visited:
            return
        visited.add(source.id)
        for dependency in source.dependencies:
            if dependency.get("type") == "run":
                await check(await get_run(db, ctx, eid, uuid.UUID(dependency["id"])))
            elif dependency.get("kind") == "tp-dataset":
                await licensed_dataset(db, ctx, eid, uuid.UUID(dependency["id"]), export=True)

    await check(run)


async def released(db, ctx, eid, run):
    records = await selected(db, ctx, eid, "release", run.inputs["profile_id"])
    matching = [x for x in records if x.body["document_run_id"] == str(run.id)]
    return matching
