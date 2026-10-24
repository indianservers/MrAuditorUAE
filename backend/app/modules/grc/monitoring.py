"""Bounded snapshot monitoring; flags, ML predictions and human conclusions stay distinct."""

import hashlib
import json
import uuid
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.models.platform import Engagement
from app.modules.accounting.models import Account, Journal, JournalLine
from app.modules.audit_execution.access import engagement_permissions
from app.modules.audit_execution.models import AuditRecord
from app.modules.grc import schemas as s
from app.modules.grc import service
from app.modules.grc.catalogue import MONITOR_RULES
from app.modules.grc.models import MonitorAlert


async def ledger_engine(db, ctx, eng, rule):
    from app.modules.audit_analytics.engine import AnalyticsEngine
    from app.modules.audit_analytics.schemas import AnalyticsRequest

    snapshot = await service.snapshot(db, ctx, eng, rule.snapshot_id)
    statement = (
        select(JournalLine, Account.code, Account.classification, Journal.reference, Account.name)
        .join(Account, Account.id == JournalLine.account_id)
        .join(Journal, Journal.id == JournalLine.journal_id)
        .where(
            JournalLine.tenant_id == ctx.tenant_id,
            JournalLine.snapshot_id == snapshot.id,
            JournalLine.entity_id == eng.entity_id,
            JournalLine.period_id == eng.period_id,
            JournalLine.opening.is_(False),
        )
        .order_by(JournalLine.id)
    )
    # Stream ORM facts to DuckDB without materializing the full population in Python.
    import csv

    from app.modules.audit_analytics.engine import COLUMNS

    population_count = 0
    ml_rows: list[dict] = []
    with TemporaryDirectory(prefix="grc-monitor-") as directory:
        path = Path(directory) / "population.csv"
        with path.open("w", newline="", encoding="utf-8") as out:
            writer = csv.DictWriter(out, fieldnames=COLUMNS)
            writer.writeheader()
            stream = await db.stream(statement)
            async for batch in stream.partitions(1000):
                for row, code, category, reference, account_name in batch:
                    population_count += 1
                    if population_count > 1000000:
                        raise HTTPException(
                            413, "Partition monitoring populations above one million lines"
                        )
                    attrs = row.attributes or {}
                    writer.writerow(
                        {
                            "id": str(row.id),
                            "account_code": code,
                            "category": category,
                            "journal_ref": reference,
                            "posting_date": str(row.posting_date),
                            "document_date": str(row.document_date) if row.document_date else None,
                            "debit": str(row.base_debit),
                            "credit": str(row.base_credit),
                            "amount": str(row.base_debit + row.base_credit),
                            "description": row.description,
                            "counterparty": row.counterparty,
                            "manual": attrs.get("manual"),
                            "posting_timestamp": attrs.get("posting_timestamp"),
                            "user": attrs.get("user"),
                            "reversal_ref": attrs.get("reversal_ref"),
                        }
                    )
                    if rule.ml_deployment_id and len(ml_rows) < rule.ml_limit:
                        ml_rows.append(
                            {
                                "id": str(row.id),
                                "journal": str(row.journal_id),
                                "client": str(row.client_id),
                                "date": str(row.posting_date),
                                "debit": float(row.base_debit),
                                "credit": float(row.base_credit),
                                "currency": row.currency,
                                "functional_currency": row.functional_currency,
                                "description": row.description,
                                "account": str(row.account_id),
                                "account_name": account_name,
                                "counterparty": row.counterparty,
                                "source_fingerprint": hashlib.sha256(
                                    json.dumps(
                                        [
                                            code,
                                            reference,
                                            str(row.posting_date),
                                            str(row.base_debit),
                                            str(row.base_credit),
                                            row.description,
                                            row.counterparty,
                                        ]
                                    ).encode()
                                ).hexdigest(),
                                **(
                                    {"manual": attrs["manual"]}
                                    if isinstance(attrs.get("manual"), bool)
                                    else {}
                                ),
                            }
                        )
        with path.open(newline="", encoding="utf-8") as source:
            engine = AnalyticsEngine(csv.DictReader(source))
        try:
            config = AnalyticsRequest.model_validate(
                {"snapshot_id": str(snapshot.id), **rule.criteria}
            )
            from starlette.concurrency import run_in_threadpool

            summary = await run_in_threadpool(engine.evaluate, config)
            code = MONITOR_RULES[rule.rule_code][2]
            selected = next((x for x in summary if x["rule_id"] == code), None)
            if not code:
                return (
                    {
                        "status": "NOT_TESTABLE",
                        "requirements": MONITOR_RULES[rule.rule_code][0],
                        "population": population_count,
                        "reason": "Required specialized source adapter is not connected",
                    },
                    [],
                    snapshot,
                    ml_rows,
                )
            condition = ""
            if rule.rule_code == "large_manual_journals":
                known = engine.db.execute("SELECT count(*) FROM p WHERE manual_known").fetchone()[0]
                if not known:
                    return (
                        {
                            "status": "NOT_TESTABLE",
                            "requirements": "Reliable manual flags",
                            "population": population_count,
                        },
                        [],
                        snapshot,
                        ml_rows,
                    )
                condition = " AND p.manual_known AND p.manual"
            flags = engine.db.execute(
                "SELECT p.id,p.account_code,p.journal_ref,p.posting_date,p.debit,p.credit,p.description,p.counterparty,f.evidence FROM flags f JOIN p ON p.id=f.id WHERE f.rule=?"
                + condition
                + " ORDER BY p.id LIMIT 10001",
                [code],
            ).fetchall()
            if len(flags) > 10000:
                raise HTTPException(
                    413, "More than 10000 alerts; partition the approved rule population"
                )
            signals = []
            for (
                identifier,
                account,
                journal,
                posting,
                debit,
                credit,
                description,
                counterparty,
                evidence,
            ) in flags:
                fingerprint = hashlib.sha256(
                    json.dumps(
                        [
                            account,
                            journal,
                            str(posting),
                            str(debit),
                            str(credit),
                            description,
                            counterparty,
                        ],
                        sort_keys=True,
                    ).encode()
                ).hexdigest()
                signals.append(
                    {
                        "source_id": identifier,
                        "fingerprint": fingerprint,
                        "deterministic": {
                            "rule": code,
                            "evidence": evidence or "",
                            "classification": "REVIEW_CANDIDATE",
                            "confirmed_misstatement": False,
                        },
                        "source": {
                            "journal_reference": journal,
                            "account_code": account,
                            "posting_date": str(posting),
                            "debit": str(debit),
                            "credit": str(credit),
                        },
                    }
                )
            return (
                {
                    "status": selected.get("status", "TESTED") if selected else "TESTED",
                    "requirements": MONITOR_RULES[rule.rule_code][0],
                    "population": population_count,
                    "matches": len(signals),
                    "rule_summary": selected,
                    "engine": "existing Phase 2 AnalyticsEngine",
                    "alert_limit": 10000,
                },
                signals,
                snapshot,
                ml_rows,
            )
        finally:
            engine.close()


async def workpaper_checks(db, ctx, eng, rule):
    today = (
        date.fromisoformat(rule.criteria["as_of"]) if rule.criteria.get("as_of") else date.today()
    )
    kinds = [
        "grc-remediation",
        "grc-closure",
        "grc-obligation",
        "grc-control",
        "grc-test",
        "grc-deficiency",
    ]
    rows = (
        await db.scalars(
            select(AuditRecord)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eng.id,
                AuditRecord.kind.in_(kinds),
                AuditRecord.status.in_(service.APPROVED),
            )
            .order_by(AuditRecord.id)
        )
    ).all()
    closed = {x.body["remediation_id"] for x in rows if x.kind == "grc-closure"}
    tested = {x.body["control_id"] for x in rows if x.kind == "grc-test"}
    target = []
    if rule.rule_code == "unresolved_findings":
        actions: dict[str, list] = {}
        for action in rows:
            if action.kind == "grc-remediation":
                actions.setdefault(action.body["deficiency_id"], []).append(str(action.id))
        target = [
            x
            for x in rows
            if x.kind == "grc-deficiency"
            and (not actions.get(str(x.id)) or any(a not in closed for a in actions[str(x.id)]))
        ]
    elif rule.rule_code in {"regulatory_deadlines", "overdue_reconciliations"}:
        target = [
            x
            for x in rows
            if x.kind == "grc-obligation"
            and (x.body.get("extension_deadline") or x.body.get("deadline"))
            and (x.body.get("extension_deadline") or x.body["deadline"]) < str(today)
            and x.body.get("filing_stage") not in {"submitted", "acknowledged"}
            and x.body["compliance_assessment"] != "supported"
            and (
                rule.rule_code != "overdue_reconciliations" or x.body["module"] == "reconciliation"
            )
        ]
    elif rule.rule_code == "missing_control_evidence":
        target = [x for x in rows if x.kind == "grc-control" and str(x.id) not in tested]
    elif rule.rule_code == "access_conflicts":
        if not rule.criteria.get("access_id"):
            return (
                {
                    "status": "NOT_TESTABLE",
                    "requirements": "Approved ERP access population and incompatible permission rules",
                },
                [],
                None,
                [],
            )
        from app.modules.grc.calculations import sod

        access = await service.record(
            db, ctx, eng.id, uuid.UUID(rule.criteria["access_id"]), "sod-access"
        )
        definition = await service.record(
            db, ctx, eng.id, uuid.UUID(access.body["rule_id"]), "sod-rule"
        )
        result = sod(
            s.SoDRule.model_validate(service.clean(definition.body)),
            s.SoDAccess.model_validate(service.clean(access.body)),
        )
        signals = [
            {
                "source_id": str(access.id),
                "fingerprint": hashlib.sha256(json.dumps(x, sort_keys=True).encode()).hexdigest(),
                "deterministic": {"rule": "SOD", "classification": "REVIEW_CANDIDATE", **x},
            }
            for x in result["conflicts"]
        ]
        return (
            {
                "status": "TESTED",
                "population": len(access.body["assignments"]),
                "matches": len(signals),
                "requirements": MONITOR_RULES[rule.rule_code][0],
            },
            signals,
            None,
            [],
        )
    else:
        return (
            {
                "status": "NOT_TESTABLE",
                "requirements": MONITOR_RULES[rule.rule_code][0],
                "reason": "Required specialized source adapter is not connected",
            },
            [],
            None,
            [],
        )
    signals = [
        {
            "source_id": str(x.id),
            "fingerprint": hashlib.sha256(
                json.dumps(service.clean(x.body), sort_keys=True).encode()
            ).hexdigest(),
            "deterministic": {
                "rule": rule.rule_code,
                "classification": "REVIEW_CANDIDATE",
                "reference": x.reference,
                "as_of": str(today),
                "confirmed_misstatement": False,
            },
        }
        for x in target
    ]
    return (
        {
            "status": "TESTED",
            "population": len(rows),
            "matches": len(signals),
            "requirements": MONITOR_RULES[rule.rule_code][0],
        },
        signals,
        None,
        [],
    )


async def execute(db, ctx, payload):
    from app.modules.demo.guard import DEMO_TENANT

    synthetic = ctx.tenant_id == DEMO_TENANT
    eid = uuid.UUID(payload["engagement_id"])
    rid = uuid.UUID(payload["rule_id"])
    await engagement_permissions(db, ctx, eid, "monitor.job.execute")
    eng = await db.scalar(
        select(Engagement).where(Engagement.tenant_id == ctx.tenant_id, Engagement.id == eid)
    )
    obj = await db.scalar(
        select(AuditRecord).where(
            AuditRecord.tenant_id == ctx.tenant_id,
            AuditRecord.engagement_id == eid,
            AuditRecord.id == rid,
            AuditRecord.kind == "grc-monitor-rule",
        )
    )
    if not eng or not obj or obj.status not in service.APPROVED:
        raise HTTPException(409, "Approved monitoring rule required")
    if eng.status.upper() in {"COMPLETED", "ARCHIVED", "CANCELLED"}:
        raise HTTPException(409, "Monitoring engagement is read-only")
    version = obj.version
    if payload.get("version") != version:
        raise HTTPException(409, "Monitoring rule version changed since dispatch")
    rule = s.MonitorRule.model_validate(service.clean(obj.body))
    if payload.get("snapshot_override_id"):
        if not rule.trigger_on_import or rule.input_kind != "ledger":
            raise HTTPException(
                403, "Import-triggered monitoring requires an approved trigger configuration"
            )
        override = await service.snapshot(db, ctx, eng, uuid.UUID(payload["snapshot_override_id"]))
        rule = rule.model_copy(update={"snapshot_id": override.id})
    result, signals, snapshot, ml_rows = await (
        ledger_engine(db, ctx, eng, rule)
        if rule.input_kind == "ledger"
        else workpaper_checks(db, ctx, eng, rule)
    )
    deps = [service.dependency(obj)]
    ml_summary: dict = {"status": "NOT_REQUESTED"}
    if rule.ml_deployment_id and ml_rows:
        from starlette.concurrency import run_in_threadpool

        from app.modules.ml.models import MLEvent
        from app.modules.ml.service import node

        await engagement_permissions(db, ctx, eid, "ml.score")
        deployment = await db.scalar(
            select(MLEvent).where(
                MLEvent.tenant_id == ctx.tenant_id,
                MLEvent.engagement_id == eid,
                MLEvent.id == rule.ml_deployment_id,
                MLEvent.kind == "deployment",
            )
        )
        latest = await db.scalar(
            select(MLEvent)
            .where(
                MLEvent.tenant_id == ctx.tenant_id,
                MLEvent.engagement_id == eid,
                MLEvent.kind == "deployment",
                MLEvent.body["family"].astext == rule.ml_family,
            )
            .order_by(MLEvent.created_at.desc(), MLEvent.id.desc())
            .limit(1)
        )
        if not deployment or not latest or deployment.id != latest.id:
            raise HTTPException(409, "Monitoring ML deployment is no longer current")
        model = await db.scalar(
            select(MLEvent).where(
                MLEvent.tenant_id == ctx.tenant_id,
                MLEvent.id == uuid.UUID(deployment.body["model_id"]),
                MLEvent.kind == "model",
            )
        )
        if not model:
            raise HTTPException(409, "Registered ML model required")
        prediction, _ = await run_in_threadpool(
            node, "infer", None, None, model.body["artifacts"], ml_rows
        )
        from app.modules.demo.guard import DEMO_TENANT
        from app.modules.ml.service import event, put_dataset

        synthetic = ctx.tenant_id == DEMO_TENANT
        held_out = {
            "rows": [{**r, "label_kind": "unknown"} for r in ml_rows],
            "split": ["test"] * len(ml_rows),
            "synthetic": synthetic,
        }
        private_source = await put_dataset(db, ctx, held_out)
        dataset = await event(
            db,
            ctx,
            eid,
            "dataset",
            {
                "object": private_source,
                "synthetic": synthetic,
                "total_rows": len(ml_rows),
                "source_rows": len(ml_rows),
                "fixture_rows": 0,
                "splits": {"test": len(ml_rows)},
                "labels": {"unknown": len(ml_rows)},
                "split_method": "Monitoring holdout only; review never moves test outcomes into training",
                "source_snapshot_id": str(snapshot.id),
                "training_eligible": False,
            },
        )
        inference = await event(
            db,
            ctx,
            eid,
            "inference",
            {
                "model_id": str(model.id),
                "dataset_id": str(dataset.id),
                "snapshot": dataset.sha256,
                "offset": 0,
                "source_snapshot_id": str(snapshot.id),
                "calibration": model.body["metrics"]["calibration"],
                **prediction,
            },
            deployment.id,
        )
        by_id = {p["transaction_id"]: p for p in prediction["predictions"]}
        ml_summary = {
            "status": "COMPLETED",
            "inference_id": str(inference.id),
            "dataset_id": str(dataset.id),
            "model_id": str(model.id),
            "deployment_id": str(deployment.id),
            "feature_schema": model.body["metrics"]["feature_schema"],
            "calibration": model.body["metrics"]["calibration"],
            "scored": len(by_id),
            "source_snapshot": str(snapshot.id),
            "drift": prediction["drift"],
            "experimental": True,
            "calibrated_probability": False,
        }
        existing = {x["source_id"]: x for x in signals}
        for row in ml_rows:
            p = by_id[row["id"]]
            p.update(
                {
                    "model_id": str(model.id),
                    "feature_schema_version": model.body["metrics"]["feature_schema"].get(
                        "version"
                    ),
                    "calibration": model.body["metrics"]["calibration"],
                    "input_snapshot": str(snapshot.id),
                    "reviewer_decision": "UNREVIEWED",
                    "inference_id": str(inference.id),
                }
            )
            if row["id"] in existing:
                existing[row["id"]]["ml"] = p
            elif p.get("signal_category") in {
                "above_calibrated_threshold",
                "exception_review_signal",
            }:
                fingerprint = row["source_fingerprint"]
                signals.append(
                    {
                        "source_id": row["id"],
                        "fingerprint": fingerprint,
                        "ml": p,
                        "deterministic": None,
                    }
                )
        deps.append(
            {
                "model_id": str(model.id),
                "deployment_id": str(deployment.id),
                "dataset_snapshot": str(snapshot.id),
            }
        )
    await engagement_permissions(db, ctx, eid, "monitor.job.execute")
    await db.refresh(obj)
    if obj.version != version or obj.status not in service.APPROVED:
        raise HTTPException(409, "Monitoring rule changed during execution")
    result["synthetic"] = synthetic
    result["synthetic_provenance"] = "guarded demo tenant" if synthetic else "operational tenant"
    result["ml"] = ml_summary
    frozen = await service.run(
        db,
        ctx,
        eid,
        "monitoring",
        {
            "rule_id": str(rid),
            "rule_version": version,
            "snapshot_id": str(snapshot.id) if snapshot else None,
            "request": payload,
        },
        result,
        deps,
        rid,
    )
    created = 0
    for item in signals:
        dedup = hashlib.sha256(
            f"{rule.rule_key}/{rule.version_number}/{item['fingerprint']}".encode()
        ).hexdigest()
        signal = {
            "deterministic": item.get("deterministic"),
            "ml": item.get("ml"),
            "source": item.get("source"),
            "human_conclusion": None,
            "synthetic": synthetic,
        }
        inserted = await db.scalar(
            insert(MonitorAlert)
            .values(
                id=uuid.uuid4(),
                tenant_id=ctx.tenant_id,
                created_by=ctx.user_id,
                engagement_id=eid,
                run_id=frozen.id,
                dedup_key=dedup,
                rule_key=rule.rule_key,
                source_id=uuid.UUID(item["source_id"]),
                snapshot_id=snapshot.id if snapshot else None,
                signals=signal,
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "engagement_id", "dedup_key"])
            .returning(MonitorAlert.id)
        )
        created += bool(inserted)
    # The execution stays immutable; insertion statistics live in a separate immutable receipt.
    receipt = await service.run(
        db,
        ctx,
        eid,
        "monitoring-receipt",
        {"run_id": str(frozen.id)},
        {
            "created_alerts": created,
            "deduplicated": len(signals) - created,
            "candidate_signals": len(signals),
        },
        deps,
        rid,
    )
    return {
        "id": str(frozen.id),
        "status": "completed",
        "created_alerts": created,
        "receipt_id": str(receipt.id),
    }
