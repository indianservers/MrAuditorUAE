"""Immutable intelligence receipts and recoverable accounting jobs."""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    common = "tenant_id UUID NOT NULL REFERENCES tenants(id), created_by UUID REFERENCES users(id), id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), engagement_id UUID NOT NULL, FOREIGN KEY(tenant_id,engagement_id) REFERENCES engagements(tenant_id,id)"
    definitions = {
        "audit_intelligence_events": "root_id UUID NOT NULL, version INTEGER NOT NULL, kind VARCHAR NOT NULL, body JSONB NOT NULL, dependencies JSONB NOT NULL, sha256 VARCHAR NOT NULL, UNIQUE(tenant_id,id), UNIQUE(tenant_id,root_id,version)",
        "audit_intelligence_jobs": "idempotency_key VARCHAR NOT NULL, operation VARCHAR NOT NULL, payload JSONB NOT NULL, payload_sha256 VARCHAR NOT NULL, status VARCHAR NOT NULL, progress INTEGER NOT NULL CHECK(progress BETWEEN 0 AND 100), attempts INTEGER NOT NULL, version INTEGER NOT NULL, result_id UUID, error_category VARCHAR, error_details JSONB, UNIQUE(tenant_id,created_by,idempotency_key)",
    }
    for name, fields in definitions.items():
        op.execute(f"CREATE TABLE {name} ({common}, {fields})")
        op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])
        op.create_index(f"ix_{name}_engagement", name, ["tenant_id", "engagement_id", "created_at"])
        op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {name} USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)"
        )
    op.execute(
        "CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON audit_intelligence_events FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )


def downgrade():
    raise RuntimeError("Preserve intelligence/evidence history; use a forward repair")
