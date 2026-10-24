import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.db.models import platform  # noqa: F401
from app.modules.accounting import models as accounting_models  # noqa: F401
from app.modules.audit_execution import models as audit_models  # noqa: F401
from app.modules.enterprise_ai import models as enterprise_ai_models  # noqa: F401
from app.modules.grc import models as grc_models  # noqa: F401
from app.modules.ifrs import models as ifrs_models  # noqa: F401
from app.modules.intelligence import models as intelligence_models  # noqa: F401
from app.modules.jurisdictions import models as jurisdiction_models  # noqa: F401
from app.modules.ml import models as ml_models  # noqa: F401
from app.modules.saas import models as saas_models  # noqa: F401
from app.modules.tax import models as tax_models  # noqa: F401
from app.modules.tp import models as tp_models  # noqa: F401
from app.modules.vat import models as vat_models  # noqa: F401

config = context.config
target_metadata = Base.metadata


def migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine = create_async_engine(settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(migrations)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
