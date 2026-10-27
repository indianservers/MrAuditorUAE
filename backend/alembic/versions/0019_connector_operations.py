"""Durable connector checkpoints, grants, event receipts and qualification evidence."""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE connector_states (
        id UUID PRIMARY KEY, tenant_id UUID NOT NULL REFERENCES tenants(id),
        created_by UUID REFERENCES users(id), created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), connection_id UUID,
        namespace VARCHAR(40) NOT NULL, key VARCHAR(128) NOT NULL, payload JSONB NOT NULL,
        expires_at TIMESTAMPTZ,
        CONSTRAINT uq_connector_state UNIQUE(tenant_id,namespace,key))""")
    op.create_index("ix_connector_states_tenant_id", "connector_states", ["tenant_id"])
    op.create_index("ix_connector_states_connection_id", "connector_states", ["connection_id"])
    op.execute("ALTER TABLE connector_states ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE connector_states FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_isolation ON connector_states
        USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
        WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)""")
    op.execute("""CREATE FUNCTION protect_connector_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF OLD.namespace IN ('profile','qualification','source_revision') THEN
        RAISE EXCEPTION 'connector evidence is immutable'; END IF; IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$""")
    op.execute(
        "CREATE TRIGGER immutable_connector_evidence BEFORE UPDATE OR DELETE ON connector_states FOR EACH ROW EXECUTE FUNCTION protect_connector_evidence()"
    )


def downgrade():
    raise RuntimeError("Preserve connector evidence; use a forward migration")
