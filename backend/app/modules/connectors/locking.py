"""Sync serialization without holding a connection row across independent storage writes."""

from sqlalchemy import select, text

from app.modules.accounting.models import Connection


async def begin_sync(db, ctx, connection_id):
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,30))"),
        {"key": str(ctx.tenant_id) + str(connection_id)},
    )


async def finish_sync(db, ctx, connection_id):
    # Same order as API admissions: tenant storage lock, then connection row.
    # All independent checkpoint object writes must have finished by this point.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,12))"), {"key": str(ctx.tenant_id)}
    )
    return await db.scalar(
        select(Connection)
        .where(Connection.tenant_id == ctx.tenant_id, Connection.id == connection_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
