"""Execution metadata shared by existing audit, intelligence and ML stores."""

import hashlib
import uuid
from importlib.metadata import version
from pathlib import Path

from sqlalchemy import select

from app.db.models.platform import Engagement, FinancialPeriod, LegalEntity
from app.modules.accounting.models import ImportBatch, ImportSnapshot

SUPPORTING_TABLE_PATHS = (
    "core/read_projection.py",
    "core/operations_contracts.py",
    "modules/intelligence/service.py",
    "modules/intelligence/schemas.py",
    "modules/intelligence/supporting_tables.py",
    "modules/intelligence/pdf_tables.py",
    "modules/intelligence/documents.py",
    "modules/ingestion/parser.py",
    "modules/accounting/schemas.py",
    "modules/lineage/storage.py",
    "modules/lineage/freshness.py",
    "modules/audit_execution/access.py",
    "modules/audit_execution/service.py",
    "modules/jurisdictions/workspace.py",
    "modules/jurisdictions/packages.py",
)

COUNTRY_WORKFLOW_PATHS = (
    *SUPPORTING_TABLE_PATHS,
    "modules/ingestion/legacy_xls.py",
    "modules/audit_execution/evidence.py",
    "core/json_documents.py",
    "api/v1/intelligence.py",
    "modules/intelligence/matching.py",
    "modules/ifrs/calculations.py",
    "modules/ifrs/schemas.py",
    "modules/jurisdictions/profiles.py",
    "modules/reconciliation/service.py",
    "modules/regulatory/conversion.py",
    "modules/regulatory/benefit_profiles.py",
    "modules/regulatory/payroll_profiles.py",
    "modules/regulatory/pension_profiles.py",
    "modules/regulatory/rule_spans.py",
    "modules/regulatory/validation.py",
    "modules/regulatory/validation_schemas.py",
    "modules/regulatory/schemas.py",
    "modules/regulatory/service.py",
    "modules/regulatory/source_documents.py",
)


def country_workflow_hash():
    """Whole trusted engine scope, including newly added readers and calculators."""
    app = Path(__file__).resolve().parents[1]
    paths = set(COUNTRY_WORKFLOW_PATHS)
    for directory in ("modules/country_workflows", "modules/vat"):
        root = app / directory
        if not root.is_dir():
            raise ValueError("Country workflow implementation directory is missing")
        paths.update(
            path.relative_to(app).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path.suffix in {".py", ".json"}
        )
    digest = hashlib.sha256(b"country-workflows/1")
    for name in sorted(paths):
        content = (app / name).read_bytes()
        digest.update(name.encode() + b"\0" + hashlib.sha256(content).digest())
    for dependency in (
        "pydantic",
        "pycountry",
        "Babel",
        "openpyxl",
        "defusedxml",
        "pypdf",
        "pypdfium2",
        "xlrd",
        "olefile",
    ):
        digest.update(dependency.encode() + b"\0" + version(dependency).encode() + b"\0")
    return digest.hexdigest()


def supporting_table_hash():
    """Trusted reader scope; saved receipts cannot choose which files are checked."""
    app = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256(b"supporting-table/1")
    for name in SUPPORTING_TABLE_PATHS:
        content = (app / name).read_bytes()
        digest.update(name.encode() + b"\0" + hashlib.sha256(content).digest())
    for dependency in ("openpyxl", "defusedxml", "pycountry", "pydantic", "pypdf", "pypdfium2"):
        digest.update(dependency.encode() + b"\0" + version(dependency).encode() + b"\0")
    return digest.hexdigest()


def country_workflow_fingerprint(db):
    """One code snapshot per database transaction; never cache across requests."""
    session = getattr(db, "sync_session", None)
    transaction = session.get_transaction() if session is not None else None
    info = getattr(db, "info", None)
    if transaction is None or not isinstance(info, dict):
        return country_workflow_hash()
    cached = info.get("_country_workflow_implementation")
    if isinstance(cached, tuple) and cached[0] is transaction:
        return cached[1]
    fingerprint = country_workflow_hash()
    info["_country_workflow_implementation"] = (transaction, fingerprint)
    return fingerprint


def implementation_current(saved, kind, *, country_fingerprint=None):
    contract = saved.get("contract_version")
    if contract == "audit-operations/1":
        expected = implementation_hash()
    elif (
        contract == "audit-operations/2"
        and kind in {"workflow-source", "country-workflow"}
        and saved.get("kind") == kind
        and saved.get("implementation_scope") == "country-workflows/1"
    ):
        expected = (
            country_fingerprint if country_fingerprint is not None else country_workflow_hash()
        )
    elif (
        contract == "audit-operations/2"
        and kind == "source-table"
        and saved.get("kind") == kind
        and saved.get("implementation_scope") == "supporting-table/1"
    ):
        expected = supporting_table_hash()
    else:
        return False
    return saved.get("implementation_sha256") == expected


def implementation_hash():
    app = Path(__file__).resolve().parents[1]
    paths = [
        "core/operations_contracts.py",
        "modules/intelligence/matching.py",
        "modules/country_workflows/operations.py",
        "modules/audit_analytics/service.py",
    ]
    paths += [
        "modules/audit_analytics/engine.py",
        "modules/country_workflows/practice_calculations.py",
        "modules/audit_execution/service.py",
        "modules/ifrs/calculations.py",
        "modules/ml/baselines.py",
        "modules/country_workflows/withholding_calculations.py",
        "modules/country_workflows/withholding_schemas.py",
        "modules/country_workflows/service.py",
        "modules/regulatory/service.py",
        "modules/regulatory/evaluation.py",
        "modules/regulatory/schemas.py",
        "modules/regulatory/conversion.py",
        "modules/regulatory/source_documents.py",
        "modules/regulatory/benefit_profiles.py",
        "modules/regulatory/payroll_profiles.py",
        "modules/regulatory/pension_profiles.py",
        "modules/regulatory/rule_spans.py",
        "modules/regulatory/validation.py",
        "modules/regulatory/validation_schemas.py",
    ]
    digest = hashlib.sha256()
    for name in paths:
        digest.update(name.encode())
        digest.update((app / name).read_bytes())
    return digest.hexdigest()


async def receipt(
    db, ctx, *, kind, body, dependencies=(), eng=None, snapshot=None, mode=None, metadata_only=False
):
    entity_id = eng.entity_id if eng else snapshot.entity_id
    period_id = eng.period_id if eng else snapshot.period_id
    entity = await db.get(LegalEntity, entity_id)
    period = await db.get(FinancialPeriod, period_id) if period_id else None
    sources = []
    ids = {d["id"] for d in dependencies if d.get("type") == "snapshot"}
    ids.update(
        s["id"] for s in body.get("source_snapshots", []) if isinstance(s, dict) and s.get("id")
    )
    if snapshot:
        ids.add(str(snapshot.id))
    for sid in sorted(ids):
        source = await db.scalar(
            select(ImportSnapshot).where(
                ImportSnapshot.tenant_id == ctx.tenant_id, ImportSnapshot.id == uuid.UUID(sid)
            )
        )
        batch = await db.get(ImportBatch, source.batch_id) if source else None
        sources.append(
            {
                "id": sid,
                "sha256": source.sha256 if source else None,
                "source_complete": bool(batch and batch.options.get("source_complete") is True),
            }
        )
    mode = mode or body.get("execution_mode", "rules_baseline")
    if mode == "deterministic_engine":
        mode = "rules_baseline"
    if mode not in {
        "trained_model",
        "statistical_baseline",
        "rules_baseline",
        "diagnostic_mock",
        "unavailable",
    }:
        mode = "unavailable"
    return {
        "contract_version": "audit-operations/2"
        if kind in {"source-table", "workflow-source", "country-workflow"}
        else "audit-operations/1",
        "implementation_scope": "supporting-table/1"
        if kind == "source-table"
        else "country-workflows/1"
        if kind in {"workflow-source", "country-workflow"}
        else "legacy-global",
        "tenant_id": str(ctx.tenant_id),
        "entity_id": str(entity_id),
        "entity_version": entity.version,
        "engagement_id": str(eng.id) if eng else None,
        "period_id": str(period_id) if period_id else None,
        "period_start": str(period.start_date) if period else None,
        "period_end": str(period.end_date) if period else None,
        "functional_currency": entity.functional_currency,
        "kind": kind,
        "execution_status": "METADATA_RECORDED"
        if metadata_only
        else "FAILED"
        if mode == "unavailable"
        else "COMPLETED",
        "execution_mode": mode,
        "version": body.get(
            "workflow_version",
            body.get("pipeline_version", body.get("algorithm_version", "audit-operations/1")),
        ),
        "implementation_sha256": supporting_table_hash()
        if kind == "source-table"
        else country_workflow_fingerprint(db)
        if kind in {"workflow-source", "country-workflow"}
        else implementation_hash(),
        "source_snapshots": sources,
        "population_completeness": body.get(
            "population_completeness",
            "DECLARED_SOURCE_SCOPE"
            if sources and all(s["source_complete"] for s in sources)
            else "UNKNOWN",
        ),
        "parameters": body.get("parameters", body.get("config", {})),
        "evidence_receipts": list(dependencies),
        "exceptions": body.get("issues", [])
        or [
            {"id": row.get("id"), "state": row["state"]}
            for row in body.get("rows", [])
            if row.get("state") and row["state"] not in {"MATCHED", "SUPPORTED", "NOT-APPLICABLE"}
        ],
        "review_status_at_execution": body.get("review_status", "UNREVIEWED"),
        "professional_conclusion": "NOT_DETERMINED",
        "actions": "NO_JOURNALS_PAYMENTS_OR_MESSAGES_EXECUTED",
    }


async def current(db, ctx, obj):
    saved = getattr(obj, "body", {}).get("operations_execution")
    if not saved:
        return True  # Existing source-specific freshness checks still govern legacy events.
    country_fingerprint = (
        country_workflow_fingerprint(db)
        if saved.get("contract_version") == "audit-operations/2"
        and saved.get("implementation_scope") == "country-workflows/1"
        and obj.kind in {"workflow-source", "country-workflow"}
        else None
    )
    from app.core.read_projection import read_once

    eng, entity, period = await read_once(db, ctx, "operations-scope", str(obj.engagement_id),
                                         lambda: _scope_objects(db, obj.engagement_id))
    return (
        implementation_current(saved, obj.kind, country_fingerprint=country_fingerprint)
        and saved.get("tenant_id") == str(ctx.tenant_id)
        and saved.get("entity_id") == str(eng.entity_id)
        and saved.get("entity_version") == entity.version
        and saved.get("period_id") == (str(eng.period_id) if eng.period_id else None)
        and saved.get("period_start") == (str(period.start_date) if period else None)
        and saved.get("period_end") == (str(period.end_date) if period else None)
        and saved.get("functional_currency") == entity.functional_currency
    )


async def _scope_objects(db, engagement_id):
    eng = await db.get(Engagement, engagement_id)
    entity = await db.get(LegalEntity, eng.entity_id)
    period = await db.get(FinancialPeriod, eng.period_id) if eng.period_id else None
    return eng, entity, period
