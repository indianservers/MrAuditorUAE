import json

from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import Context
from app.db.models.platform import AIModelConfiguration, AIProviderConfig
from app.modules.accounting.models import (
    Account,
    AnalyticsRun,
    FinancialSuggestion,
    Finding,
    ImportBatch,
    ImportSnapshot,
    JournalLine,
)
from app.modules.accounting.service import scope_values, scoped
from app.modules.ai_engine.service import execute
from app.modules.financial_ai.schemas import (
    OUTPUTS,
    FinancialGatewayRequest,
    FinancialRequest,
    GatewayInput,
)
from app.modules.reconciliation.service import balance


async def suggest(
    db: AsyncSession, ctx: Context, task: str, request: FinancialRequest, request_id: str
):
    snapshot = await scoped(db, ctx, ImportSnapshot, request.snapshot_id)
    batch = await scoped(db, ctx, ImportBatch, snapshot.batch_id)
    if batch.status not in {"active", "superseded"}:
        raise HTTPException(409, "Committed accounting snapshot required")
    configured_model = await db.scalar(select(AIModelConfiguration).where(
        AIModelConfiguration.name == request.model, AIModelConfiguration.enabled.is_(True)
    ))
    provider = await db.get(AIProviderConfig, configured_model.provider_id) if configured_model else None
    if not provider:
        raise HTTPException(422, "Approved AI model required")
    if provider.adapter != "mock" and not settings().audit_ai_external_approved:
        raise HTTPException(403, "Approved external financial disclosure required")
    evidence: dict = {
        "evidence_ids": [str(snapshot.id)],
        "snapshot": str(snapshot.id),
        "task": task,
        "assertions": request.assertions,
    }
    allowed = {snapshot.id}
    if request.account_id:
        account = await scoped(db, ctx, Account, request.account_id)
        if account.entity_id != snapshot.entity_id:
            raise HTTPException(404, "Account not in snapshot entity")
        evidence["account"] = {
            "name": account.name,
            "classification": account.classification,
            "source_group": account.source_group,
        }
        allowed.add(account.id)
    if request.line_ids:
        lines = []
        for identifier in request.line_ids:
            line = await scoped(db, ctx, JournalLine, identifier)
            if line.snapshot_id != snapshot.id:
                raise HTTPException(404, "Transaction outside evidence snapshot")
            # Party names and narrations are excluded by default; bounded metadata only.
            lines.append(
                {
                    "id": str(line.id),
                    "debit": str(line.base_debit),
                    "credit": str(line.base_credit),
                    "date": str(line.posting_date),
                }
            )
            allowed.add(line.id)
        evidence["transactions"] = lines
    if request.analytics_run_id:
        run = await scoped(db, ctx, AnalyticsRun, request.analytics_run_id)
        if run.snapshot_id != snapshot.id:
            raise HTTPException(422, "Rule result scope mismatch")
        findings = (
            await db.scalars(
                select(Finding)
                .where(
                    Finding.tenant_id == ctx.tenant_id,
                    Finding.run_id == run.id,
                    Finding.line_id.in_(request.line_ids),
                )
                .limit(20)
            )
        ).all()
        evidence["indicators"] = [{"rule_id": f.rule_id, "evidence": f.evidence} for f in findings]
    if task == "financial_commentary":
        current = await balance(db, ctx, snapshot.id)
        evidence["current"] = [
            {"account": r["code"], "closing": str(r["closing"])} for r in current["lines"][:20]
        ]
        if request.prior_snapshot_id:
            prior = await scoped(db, ctx, ImportSnapshot, request.prior_snapshot_id)
            if prior.entity_id != snapshot.entity_id:
                raise HTTPException(404, "Prior snapshot scope mismatch")
            previous = await balance(db, ctx, prior.id)
            if previous["functional_currency"] != current["functional_currency"]:
                raise HTTPException(422, "Commentary currencies differ")
            from app.modules.accounting.calculations import movements

            evidence["movements"] = movements(
                {r["code"]: r["closing"] for r in current["lines"]},
                {r["code"]: r["closing"] for r in previous["lines"]},
            )[:20]
            allowed.add(prior.id)
    evidence["evidence_ids"] = [str(i) for i in sorted(allowed, key=str)]
    # Enforce a tenant-level request budget in addition to per-call output-token caps.
    async with Redis.from_url(settings().redis_url) as redis:
        count = await redis.eval(
            "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],3600) end; return n",
            1,
            "financial-ai-budget:" + str(ctx.tenant_id),
        )
        if count > settings().financial_ai_hourly_requests:
            raise HTTPException(429, "Tenant AI request budget exceeded")
    gateway = FinancialGatewayRequest(
        task_type=task, input=GatewayInput(text=json.dumps(evidence)), model=request.model
    )
    result = await execute(db, ctx, gateway, request_id)
    if result["status"] != "completed":
        return result
    output = OUTPUTS[task].model_validate(result["output"])
    if not set(output.citations) <= allowed:
        from app.db.models.platform import AIExecution

        execution = await scoped(db, ctx, AIExecution, result["execution_id"])
        execution.status = "failed"
        execution.error_category = "invalid_citation"
        await db.flush()
        return {
            "execution_id": str(execution.id),
            "status": "failed",
            "output": None,
            "error_category": "invalid_citation",
        }
    suggestion = FinancialSuggestion(
        **scope_values(snapshot),
        execution_id=result["execution_id"],
        snapshot_id=snapshot.id,
        task=task,
        suggestion=output.model_dump(mode="json"),
    )
    db.add(suggestion)
    await db.flush()
    from app.db.models.platform import AIExecution, PromptTemplate

    execution = await scoped(db, ctx, AIExecution, result["execution_id"])
    template = await db.get(PromptTemplate, execution.template_id)
    return {
        "suggestion_id": str(suggestion.id),
        "execution_id": str(result["execution_id"]),
        "model": request.model,
        "execution_mode": result["execution_mode"],
        "provider_adapter": result["provider_adapter"],
        "prompt_version": template.version if template else None,
        "review_status": "pending_review",
        "output": output.model_dump(mode="json"),
    }
