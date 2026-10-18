import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Context
from app.modules.accounting.models import (
    AnalyticsRun,
    AuditRule,
    Finding,
    ImportBatch,
    ImportSnapshot,
    RiskScore,
    RuleResult,
    SamplingItem,
    SamplingRun,
)
from app.modules.accounting.schemas import SamplingRequest
from app.modules.accounting.service import scope_values, scoped
from app.modules.audit_analytics.engine import RULES, VERSION, AnalyticsEngine
from app.modules.audit_analytics.schemas import AnalyticsRequest


async def population(db: AsyncSession, ctx: Context, snapshot_id: uuid.UUID):
    snapshot = await scoped(db, ctx, ImportSnapshot, snapshot_id)
    batch = await scoped(db, ctx, ImportBatch, snapshot.batch_id)
    if batch.status not in {"active", "superseded"} or batch.kind not in {"gl", "journals"}:
        raise HTTPException(409, "Committed journal-level snapshot required")
    query = text("""SELECT l.id,a.code account_code,j.reference journal_ref,l.posting_date,l.document_date,
    l.attributes->>'posting_timestamp' posting_timestamp,l.base_debit debit,l.base_credit credit,l.description,l.counterparty,
    l.attributes->>'user' AS "user",l.attributes->>'manual' manual,l.attributes->>'reversal_ref' reversal_ref,
    a.classification category,a.contra,a.source_group FROM journal_lines l JOIN accounts a ON a.id=l.account_id AND a.tenant_id=l.tenant_id
    JOIN journal_entries j ON j.id=l.journal_id AND j.tenant_id=l.tenant_id
    WHERE l.tenant_id=:tenant AND l.snapshot_id=:snapshot AND NOT l.opening ORDER BY l.id""")
    # Server-side cursor fetches bounded batches; DuckDB owns the temporary population.
    result = await db.stream(query, {"tenant": ctx.tenant_id, "snapshot": snapshot_id})
    return snapshot, result


async def analytics(
    db: AsyncSession, ctx: Context, request: AnalyticsRequest, run_id: uuid.UUID | None = None
):
    snapshot, stream = await population(db, ctx, request.snapshot_id)
    # Bounded Arrow/CSV spooling separates async DB fetch from synchronous rule execution.
    import csv
    import tempfile
    from pathlib import Path

    from app.modules.audit_analytics.engine import COLUMNS

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "population.csv"
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=[c for c in COLUMNS if c != "amount"])
            writer.writeheader()
            async for partition in stream.mappings().partitions(1000):
                writer.writerows(dict(row) for row in partition)
        with path.open(newline="", encoding="utf-8") as file:
            engine = AnalyticsEngine(csv.DictReader(file))
        try:
            run = (
                await scoped(db, ctx, AnalyticsRun, run_id, True)
                if run_id
                else AnalyticsRun(
                    **scope_values(snapshot),
                    snapshot_id=snapshot.id,
                    parameters=request.model_dump(mode="json"),
                )
            )
            if run_id and run.status == "completed":
                return {"id": run.id, "status": run.status}
            if not run_id:
                db.add(run)
                await db.flush()
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            await db.execute(
                pg_insert(AuditRule)
                .values(
                    [
                        dict(
                            id=uuid.uuid4(),
                            tenant_id=ctx.tenant_id,
                            created_by=ctx.user_id,
                            code=code,
                            version=VERSION,
                            definition={"name": name, "requires": requires},
                        )
                        for code, name, requires in RULES
                    ]
                )
                .on_conflict_do_nothing(index_elements=["tenant_id", "code", "version"])
            )
            mapping_evidence = engine.db.execute(
                "SELECT DISTINCT account_code,category,contra,source_group FROM p ORDER BY account_code"
            ).fetchall()
            run.parameters = {
                **run.parameters,
                "account_mapping_snapshot": [list(row) for row in mapping_evidence],
            }
            results = engine.evaluate(request)
            for r in results:
                db.add(
                    RuleResult(
                        **scope_values(snapshot),
                        run_id=run.id,
                        rule_id=r["rule_id"],
                        rule_version=VERSION,
                        result=r,
                    )
                )
            for chunk in engine.flags():
                await db.execute(
                    insert(Finding),
                    [
                        dict(
                            id=uuid.uuid4(),
                            **scope_values(snapshot),
                            run_id=run.id,
                            line_id=uuid.UUID(identifier),
                            rule_id=code,
                            status="requires_review",
                            evidence={
                                "indicator": evidence,
                                "ruleset_version": VERSION,
                                "not_a_fraud_conclusion": True,
                            },
                        )
                        for code, identifier, evidence in chunk
                    ],
                )
            for chunk in engine.scores(request.weights):
                await db.execute(
                    insert(RiskScore),
                    [
                        dict(
                            id=uuid.uuid4(),
                            **scope_values(snapshot),
                            run_id=run.id,
                            line_id=uuid.UUID(identifier),
                            score=score["score"],
                            band=score["band"],
                            factors={**score, "score": str(score["score"])},
                        )
                        for identifier, score in chunk
                    ],
                )
            run.status = "completed"
            run.progress = 100
            await db.flush()
            return {"id": run.id, "status": run.status, "result": {"rules": results}}
        finally:
            engine.close()


async def sampling(db: AsyncSession, ctx: Context, request: SamplingRequest):
    import csv
    import random
    import tempfile
    from pathlib import Path

    from app.modules.audit_analytics.engine import COLUMNS

    snapshot, stream = await population(db, ctx, request.snapshot_id)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "sampling.csv"
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=[c for c in COLUMNS if c != "amount"])
            writer.writeheader()
            async for partition in stream.mappings().partitions(1000):
                writer.writerows(dict(row) for row in partition)
        with path.open(newline="", encoding="utf-8") as file:
            engine = AnalyticsEngine(csv.DictReader(file))
        try:
            count = engine.count
            size = min(count, request.size)
            excluded_zero = excluded_negative = 0
            params: list[Any] = []
            if request.method == "full":
                query = "SELECT id,1 hits FROM p ORDER BY id"
            elif request.method == "judgmental":
                if not request.selected_line_ids or not request.selection_rationale.strip():
                    raise HTTPException(
                        422,
                        "Judgmental selection requires documented rationale and explicit population items",
                    )
                chosen = sorted({str(i) for i in request.selected_line_ids})
                placeholders = ",".join("?" for _ in chosen)
                matched = engine.db.execute(
                    "SELECT count(*) FROM p WHERE id IN (" + placeholders + ")", chosen
                ).fetchone()[0]
                if matched != len(chosen):
                    raise HTTPException(422, "Judgmental item outside the source population")
                query = "SELECT id,1 hits FROM p WHERE id IN (" + placeholders + ") ORDER BY id"
                params = chosen
            elif request.method == "high_value":
                query = "SELECT id,1 hits FROM p WHERE amount>=? ORDER BY id"
                params = [request.threshold]
            elif request.method == "random":
                # Versioned stable pseudo-random permutation; no in-memory population list.
                query = "SELECT id,1 hits FROM p ORDER BY md5(id||?),id LIMIT ?"
                params = [str(request.seed), size]
            elif request.method == "systematic":
                if size == 0:
                    query = "SELECT id,1 hits FROM p WHERE false"
                else:
                    start = random.Random(request.seed).randrange(10**9)
                    query = "SELECT p.id,1 hits FROM (SELECT id,row_number() OVER(ORDER BY id)-1 rn FROM p) p JOIN (SELECT ((?+range*1000000000)::HUGEINT*? // (?::HUGEINT*1000000000)) AS picked_index FROM range(?)) points ON p.rn=points.picked_index ORDER BY p.id"
                    params = [start, count, size, size]
            elif request.method == "mus":
                excluded_zero, excluded_negative = engine.db.execute(
                    "SELECT count(*) FILTER(WHERE debit-credit=0),count(*) FILTER(WHERE debit-credit<0) FROM p"
                ).fetchone()
                engine.db.execute(
                    "CREATE TABLE monetary AS SELECT id,cast((debit-credit)*100000000 AS HUGEINT) units FROM p WHERE debit-credit>0"
                )
                total = engine.db.execute("SELECT sum(units) FROM monetary").fetchone()[0]
                if not total:
                    raise HTTPException(
                        422,
                        "MUS requires positive monetary values; negative and zero lines excluded explicitly",
                    )
                start = random.Random(request.seed).randrange(int(total))
                engine.db.execute(
                    "CREATE TABLE cumulative AS SELECT id,sum(units) OVER(ORDER BY id)*? upper_bound FROM monetary",
                    [request.size],
                )
                # Exact rational systematic PPS points, ASOF chooses next cumulative boundary.
                query = "SELECT id,count(*) hits FROM (SELECT ?::HUGEINT+range*?::HUGEINT point FROM range(?)) targets ASOF JOIN cumulative ON targets.point<cumulative.upper_bound GROUP BY id ORDER BY id"
                params = [start, int(total), request.size]
            else:
                if not request.analytics_run_id:
                    raise HTTPException(422, "Risk sampling requires an analytics run")
                previous = await scoped(db, ctx, AnalyticsRun, request.analytics_run_id)
                if previous.snapshot_id != snapshot.id:
                    raise HTTPException(422, "Risk population mismatch")
                engine.db.execute("CREATE TABLE risks(id VARCHAR,score DECIMAL(6,3))")
                scores = await db.stream(
                    select(RiskScore.line_id, RiskScore.score).where(
                        RiskScore.tenant_id == ctx.tenant_id, RiskScore.run_id == previous.id
                    )
                )
                async for chunk in scores.partitions(1000):
                    engine.db.executemany(
                        "INSERT INTO risks VALUES (?,?)", [(str(i), score) for i, score in chunk]
                    )
                query = "SELECT p.id,1 hits FROM p LEFT JOIN risks USING(id) ORDER BY coalesce(score,0) DESC,p.id LIMIT ?"
                params = [size]
            result = {
                "population": count,
                "seed": request.seed,
                "algorithm_version": "duckdb-exact-selection/2.0.0",
                "excluded_zero": excluded_zero,
                "excluded_negative": excluded_negative,
                "assurance": "Professional sample-size decision; no ISA assurance claimed",
            }
            run = SamplingRun(
                **scope_values(snapshot),
                snapshot_id=snapshot.id,
                method=request.method,
                seed=request.seed,
                parameters=request.model_dump(mode="json"),
                result=result,
            )
            db.add(run)
            await db.flush()
            cursor = engine.db.execute(query, params)
            selected_count = 0
            while chunk := cursor.fetchmany(1000):
                selected_count += len(chunk)
                await db.execute(
                    insert(SamplingItem),
                    [
                        dict(
                            id=uuid.uuid4(),
                            **scope_values(snapshot),
                            run_id=run.id,
                            line_id=uuid.UUID(identifier),
                            hits=hits,
                        )
                        for identifier, hits in chunk
                    ],
                )
            return {
                "id": run.id,
                "status": "completed",
                "result": {**result, "selected_count": selected_count},
            }
        finally:
            engine.close()
