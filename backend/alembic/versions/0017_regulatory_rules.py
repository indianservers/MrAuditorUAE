"""Append-only regulatory rule proposals and controlled publication history."""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    common = "tenant_id UUID NOT NULL REFERENCES tenants(id),created_by UUID REFERENCES users(id),id UUID PRIMARY KEY,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),rule_key VARCHAR NOT NULL"
    tables = {
        "regulatory_rule_versions": "country VARCHAR NOT NULL,version INTEGER NOT NULL,body JSONB NOT NULL,sha256 VARCHAR NOT NULL,UNIQUE(tenant_id,id),UNIQUE(tenant_id,rule_key,version)",
        "regulatory_rule_actions": "version_id UUID NOT NULL,sequence INTEGER NOT NULL,state VARCHAR NOT NULL,body JSONB NOT NULL,UNIQUE(tenant_id,rule_key,sequence),FOREIGN KEY(tenant_id,version_id) REFERENCES regulatory_rule_versions(tenant_id,id)",
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
            f"CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
        )


def downgrade():
    raise RuntimeError("Preserve regulatory publication history; use a forward repair")
