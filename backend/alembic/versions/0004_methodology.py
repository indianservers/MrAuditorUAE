"""Immutable versioned methodology profiles."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE audit_methodology_versions (id UUID PRIMARY KEY, tenant_id UUID NOT NULL REFERENCES tenants(id), created_by UUID REFERENCES users(id), created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), name VARCHAR NOT NULL, version INTEGER NOT NULL, effective_from TIMESTAMPTZ NOT NULL, profile JSONB NOT NULL, UNIQUE(tenant_id,name,version))"
    )
    op.execute(
        "CREATE INDEX ix_audit_methodology_versions_tenant_id ON audit_methodology_versions(tenant_id)"
    )
    op.execute("ALTER TABLE audit_methodology_versions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_methodology_versions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_methodology_versions USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON audit_methodology_versions FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )


def downgrade():
    raise RuntimeError("Methodology history is retained; restore a verified backup for rollback")
