"""Execution metadata shared by existing audit, intelligence and ML stores."""

import hashlib
import uuid
from pathlib import Path

from sqlalchemy import select

from app.db.models.platform import Engagement, FinancialPeriod, LegalEntity
from app.modules.accounting.models import ImportBatch, ImportSnapshot


def implementation_hash():
    app = Path(__file__).resolve().parents[1]
    paths = ["core/operations_contracts.py", "modules/intelligence/matching.py",
             "modules/country_workflows/operations.py", "modules/audit_analytics/service.py"]
    digest = hashlib.sha256()
    for name in paths:
        digest.update(name.encode())
        digest.update((app / name).read_bytes())
    return digest.hexdigest()


async def receipt(db, ctx, *, kind, body, dependencies=(), eng=None, snapshot=None):
    entity_id = eng.entity_id if eng else snapshot.entity_id
    period_id = eng.period_id if eng else snapshot.period_id
    entity = await db.get(LegalEntity, entity_id)
    period = await db.get(FinancialPeriod, period_id) if period_id else None
    sources = []
    ids = {d["id"] for d in dependencies if d.get("type") == "snapshot"}
    if snapshot:
        ids.add(str(snapshot.id))
    for sid in sorted(ids):
        source = await db.scalar(select(ImportSnapshot).where(ImportSnapshot.tenant_id == ctx.tenant_id, ImportSnapshot.id == uuid.UUID(sid)))
        batch = await db.get(ImportBatch, source.batch_id) if source else None
        sources.append({"id": sid, "sha256": source.sha256 if source else None,
                        "source_complete": bool(batch and batch.options.get("source_complete") is True)})
    mode = body.get("execution_mode", "rules_baseline")
    if mode == "deterministic_engine":
        mode = "rules_baseline"
    if mode not in {"trained_model", "statistical_baseline", "rules_baseline", "diagnostic_mock", "unavailable"}:
        mode = "unavailable"
    return {"contract_version": "audit-operations/1", "tenant_id": str(ctx.tenant_id),
            "entity_id": str(entity_id), "entity_version": entity.version,
            "engagement_id": str(eng.id) if eng else None, "period_id": str(period_id) if period_id else None,
            "period_start": str(period.start_date) if period else None, "period_end": str(period.end_date) if period else None,
            "functional_currency": entity.functional_currency, "kind": kind,
            "execution_status": "FAILED" if mode == "unavailable" else "COMPLETED",
            "execution_mode": mode, "version": body.get("workflow_version", body.get("pipeline_version", body.get("algorithm_version", "audit-operations/1"))),
            "implementation_sha256": implementation_hash(), "source_snapshots": sources,
            "population_completeness": body.get("population_completeness", "DECLARED_SOURCE_SCOPE" if sources and all(s["source_complete"] for s in sources) else "UNKNOWN"),
            "parameters": body.get("parameters", body.get("config", {})),
            "evidence_receipts": list(dependencies), "exceptions": body.get("issues", []),
            "review_status_at_execution": body.get("review_status", "UNREVIEWED"),
            "professional_conclusion": "NOT_DETERMINED", "actions": "NO_JOURNALS_PAYMENTS_OR_MESSAGES_EXECUTED"}


async def current(db, ctx, obj):
    saved = obj.body.get("operations_execution")
    if not saved:
        return True  # Existing source-specific freshness checks still govern legacy events.
    eng = await db.get(Engagement, obj.engagement_id)
    entity = await db.get(LegalEntity, eng.entity_id)
    period = await db.get(FinancialPeriod, eng.period_id) if eng.period_id else None
    return (saved.get("implementation_sha256") == implementation_hash()
            and saved.get("tenant_id") == str(ctx.tenant_id)
            and saved.get("entity_id") == str(eng.entity_id)
            and saved.get("entity_version") == entity.version
            and saved.get("period_id") == (str(eng.period_id) if eng.period_id else None)
            and saved.get("period_start") == (str(period.start_date) if period else None)
            and saved.get("period_end") == (str(period.end_date) if period else None)
            and saved.get("functional_currency") == entity.functional_currency)
