"""Deployment-only technical AI configuration; credentials stay in secret injection."""

import asyncio

from sqlalchemy import select

from app.core.config import settings
from app.db.models.platform import AIModelConfiguration, AIProviderConfig
from app.db.session import Session, engine


async def configure_ai() -> None:
    config = settings()
    if not config.ai_model:
        raise SystemExit("Set AI_MODEL; secrets must be injected as AI_API_KEY")
    async with Session() as db, db.begin():
        provider = await db.scalar(
            select(AIProviderConfig).where(
                AIProviderConfig.name == "Configured compatible provider"
            )
        )
        if provider is None:
            provider = AIProviderConfig(
                name="Configured compatible provider",
                adapter="openai-compatible",
                credential_reference="env:AI_API_KEY",
            )
            db.add(provider)
            await db.flush()
        model = await db.scalar(
            select(AIModelConfiguration).where(AIModelConfiguration.name == config.ai_model)
        )
        if model is None:
            db.add(
                AIModelConfiguration(
                    provider_id=provider.id,
                    name=config.ai_model,
                    enabled=True,
                    max_tokens=config.ai_max_tokens,
                )
            )
        else:
            if model.provider_id != provider.id:
                raise SystemExit("Model name already belongs to a different adapter")
            model.max_tokens = config.ai_max_tokens
            model.enabled = True
    await engine.dispose()
    print("Configured approved model. Connectivity has not been tested.")


if __name__ == "__main__":
    asyncio.run(configure_ai())
