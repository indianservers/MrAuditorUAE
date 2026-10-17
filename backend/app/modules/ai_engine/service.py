import asyncio
import time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import Context
from app.db.models.platform import (
    AIExecution,
    AIModelConfiguration,
    AIProviderConfig,
    AIUsageRecord,
    PromptTemplate,
)
from app.infrastructure.ai_providers.adapters import MockProvider, OpenAICompatibleProvider
from app.modules.ai_engine.schemas import AIProvider, AIRequest, ExecuteRequest
from app.modules.audit_log.service import record
from app.modules.financial_ai.schemas import FinancialGatewayRequest


async def execute(
    db: AsyncSession, ctx: Context, data: ExecuteRequest | FinancialGatewayRequest, request_id: str
):
    model = await db.scalar(
        select(AIModelConfiguration).where(
            AIModelConfiguration.name == data.model, AIModelConfiguration.enabled.is_(True)
        )
    )
    if not model:
        raise HTTPException(422, "Model is not approved")
    provider_config = await db.get(AIProviderConfig, model.provider_id)
    template = await db.scalar(
        select(PromptTemplate)
        .where(PromptTemplate.name == data.task_type)
        .order_by(PromptTemplate.version.desc())
        .limit(1)
    )
    if not provider_config or not template:
        raise HTTPException(503, "AI configuration unavailable")
    config = settings()
    provider: AIProvider
    if provider_config.adapter == "mock":
        provider = MockProvider()
    elif provider_config.adapter == "openai-compatible" and model.name == config.ai_model:
        provider = OpenAICompatibleProvider(
            config.ai_base_url, config.ai_api_key, config.ai_timeout_seconds
        )
    else:
        raise HTTPException(503, "Provider not configured")
    execution = AIExecution(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        model_id=model.id,
        template_id=template.id,
        request_id=request_id,
    )
    db.add(execution)
    await db.flush()
    start = time.monotonic()
    result = None
    try:
        async with asyncio.timeout(config.ai_timeout_seconds * 3 + 2):
            result = await provider.generate(
                AIRequest(
                    task_type=data.task_type,
                    text=data.input.text,
                    model=model.name,
                    system_prompt=template.content,
                    max_tokens=min(config.ai_max_tokens, model.max_tokens),
                    request_id=request_id,
                )
            )
        execution.status = "completed"
        db.add(
            AIUsageRecord(
                tenant_id=ctx.tenant_id,
                created_by=ctx.user_id,
                execution_id=execution.id,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                usage_source=result.usage_source,
            )
        )
    except Exception as exc:
        execution.status = "failed"
        execution.error_category = (
            "timeout" if isinstance(exc, TimeoutError) else "provider_or_validation"
        )
    execution.duration_ms = int((time.monotonic() - start) * 1000)
    record(db, ctx, "ai." + execution.status, execution.id, request_id)
    await db.flush()
    return {
        "execution_id": execution.id,
        "status": execution.status,
        "output": result.output if result else None,
        "error_category": execution.error_category,
    }
