"""Immutable tenant reference documents for regulatory source verification."""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE regulatory_source_documents (
        tenant_id UUID NOT NULL REFERENCES tenants(id), created_by UUID REFERENCES users(id),
        id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        title VARCHAR NOT NULL, country VARCHAR NOT NULL, source_url VARCHAR NOT NULL,
        retrieved_on DATE NOT NULL, filename VARCHAR NOT NULL, media_type VARCHAR NOT NULL,
        object_key VARCHAR NOT NULL, object_version VARCHAR NOT NULL, sha256 VARCHAR NOT NULL,
        size INTEGER NOT NULL CHECK (size > 0 AND size <= 10485760),
        scan_status VARCHAR NOT NULL CHECK (scan_status = 'CLEAN'), UNIQUE(tenant_id,id)
    )""")
    op.create_index(
        "ix_regulatory_source_documents_tenant_id", "regulatory_source_documents", ["tenant_id"]
    )
    op.execute("ALTER TABLE regulatory_source_documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE regulatory_source_documents FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_isolation ON regulatory_source_documents
        USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
        WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)""")
    op.execute("""CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON regulatory_source_documents
        FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()""")


def downgrade():
    raise RuntimeError("Preserve retained regulatory sources; use a reviewed forward migration")
