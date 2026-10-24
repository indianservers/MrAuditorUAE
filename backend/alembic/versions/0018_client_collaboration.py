"""Request-scoped expiring client links and immutable client responses."""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    common = "tenant_id UUID NOT NULL REFERENCES tenants(id),created_by UUID REFERENCES users(id),id UUID PRIMARY KEY,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    tables = {
        "client_collaboration_links": "engagement_id UUID NOT NULL,request_id UUID NOT NULL,request_version INTEGER NOT NULL,token_hash VARCHAR NOT NULL,expires_at TIMESTAMPTZ NOT NULL,retain_until DATE NOT NULL,revoked BOOLEAN NOT NULL,version INTEGER NOT NULL,responses INTEGER NOT NULL,uploads INTEGER NOT NULL,limits JSONB NOT NULL,UNIQUE(tenant_id,id),FOREIGN KEY(tenant_id,engagement_id) REFERENCES engagements(tenant_id,id),FOREIGN KEY(tenant_id,request_id) REFERENCES audit_records(tenant_id,id)",
        "client_collaboration_submissions": "link_id UUID NOT NULL,kind VARCHAR NOT NULL,body JSONB NOT NULL,FOREIGN KEY(tenant_id,link_id) REFERENCES client_collaboration_links(tenant_id,id)",
    }
    for name, fields in tables.items():
        op.execute(f"CREATE TABLE {name} ({common},{fields})")
        op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])
        op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {name} USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)"
        )
    op.execute(
        "CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON client_collaboration_submissions FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )


def downgrade():
    raise RuntimeError("Preserve client communication and evidence history; use a forward repair")
