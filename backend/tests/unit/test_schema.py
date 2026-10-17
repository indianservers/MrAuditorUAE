from pathlib import Path

from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateTable

from app.db.base import Base
from app.db.models import platform  # noqa: F401


def test_all_22_tables_compile_for_postgres():
    assert len([m for m in Base.registry.mappers if m.class_.__module__ == platform.__name__]) == 22
    for table in Base.metadata.sorted_tables:
        sql = str(CreateTable(table).compile(dialect=dialect()))
        assert "CREATE TABLE" in sql
        if "created_at" in table.c:
            assert "TIMESTAMP WITH TIME ZONE" in sql


def test_composite_tenant_foreign_keys():
    for name in [
        "legal_entities",
        "entity_relationships",
        "financial_periods",
        "engagements",
        "engagement_team_members",
        "ai_usage_records",
    ]:
        table = Base.metadata.tables[name]
        assert any(
            len(fk.columns) == 2 and "tenant_id" in fk.columns
            for fk in table.foreign_key_constraints
        )


def test_frozen_migration_has_rls_and_no_create_all():
    source = Path("alembic/versions/0001_foundation.py").read_text()
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "WITH CHECK" in source
    assert "reject_audit_mutation" in source
    assert "create_all" not in source
