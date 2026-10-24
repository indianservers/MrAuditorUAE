"""Add scoped organization defaults, append-only context decisions and graph preferences."""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    common = "tenant_id UUID NOT NULL REFERENCES tenants(id), created_by UUID REFERENCES users(id), id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    fields = {
        "organization_jurisdictions": "country VARCHAR NOT NULL, version INTEGER NOT NULL, UNIQUE(tenant_id)",
        "reporting_context_events": "engagement_id UUID NOT NULL, kind VARCHAR NOT NULL, body JSONB NOT NULL, FOREIGN KEY(tenant_id,engagement_id) REFERENCES engagements(tenant_id,id)",
        "audit_graph_layouts": "engagement_id UUID NOT NULL, user_id UUID NOT NULL REFERENCES users(id), version INTEGER NOT NULL, body JSONB NOT NULL, UNIQUE(tenant_id,engagement_id,user_id), FOREIGN KEY(tenant_id,engagement_id) REFERENCES engagements(tenant_id,id)",
        "global_group_relationships": "parent_id UUID NOT NULL, child_id UUID NOT NULL, body JSONB NOT NULL, status VARCHAR NOT NULL, version INTEGER NOT NULL, FOREIGN KEY(tenant_id,parent_id) REFERENCES legal_entities(tenant_id,id), FOREIGN KEY(tenant_id,child_id) REFERENCES legal_entities(tenant_id,id)",
    }
    for name, extra in fields.items():
        op.execute(f"CREATE TABLE {name} ({common}, {extra})")
        op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])
        op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {name} USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)"
        )
    op.execute(
        "CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON reporting_context_events FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )


def downgrade():
    raise RuntimeError("Retain reporting decisions and jurisdiction history; use a forward repair")
