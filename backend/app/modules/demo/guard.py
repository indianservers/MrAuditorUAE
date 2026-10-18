"""Fail closed before any synthetic-data mutation; never infer authorization from a URL alone."""

import uuid

from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.models.platform import Tenant

DEMO_TENANT = uuid.uuid5(uuid.NAMESPACE_DNS, "auditos.phase7.synthetic.demo.v1")
DEMO_NAME = "AuditOS Demo Chartered Accountants [SYNTHETIC]"


def configuration_guard(config):
    url = make_url(config.database_url)
    if config.environment not in {"development", "test"} or not config.synthetic_data_enabled:
        raise ValueError(
            "Synthetic data requires development/test mode and SYNTHETIC_DATA_ENABLED=true"
        )
    if not config.demo_database_name.startswith(
        "auditos_"
    ) or not config.demo_database_name.endswith("_demo"):
        raise ValueError("Explicit dedicated auditos_*_demo database required")
    if url.database != config.demo_database_name or config.demo_tenant_id != str(DEMO_TENANT):
        raise ValueError("Configured database or demo tenant identity mismatch")


async def guard(db, allow_new=False):
    config = settings()
    configuration_guard(config)
    if await db.scalar(text("SELECT current_database()")) != config.demo_database_name:
        raise ValueError("Connected database identity mismatch")
    tenant = await db.scalar(select(Tenant).where(Tenant.id == DEMO_TENANT))
    if tenant is None and not allow_new:
        raise ValueError("Explicit synthetic tenant does not exist")
    if tenant and (tenant.name != DEMO_NAME or tenant.status != "active"):
        raise ValueError("Target tenant is not the expected active demo tenant")
    return tenant


def test_database_guard(config, actual_database):
    expected = make_url(config.database_url).database
    if (
        config.environment not in {"development", "test"}
        or not expected
        or not expected.endswith("_test")
        or actual_database != expected
    ):
        raise ValueError(
            "Destructive fixtures require an explicitly configured disposable *_test database"
        )
