"""MFA session binding and operational SaaS metadata."""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN mfa_secret TEXT")
    op.execute("ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE users ADD COLUMN mfa_last_counter INTEGER NOT NULL DEFAULT -1")
    op.execute(
        "ALTER TABLE refresh_sessions ADD COLUMN mfa_verified BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "\nCREATE TABLE platform_operators (\n\tuser_id UUID NOT NULL, \n\tactive BOOLEAN NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (user_id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE tenant_subscriptions (\n\tplan VARCHAR NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tvalid_until TIMESTAMP WITH TIME ZONE NOT NULL, \n\tgrace_until TIMESTAMP WITH TIME ZONE NOT NULL, \n\tlimits JSONB NOT NULL, \n\tfeatures JSONB NOT NULL, \n\tversion INTEGER NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_tenant_subscriptions_tenant_id ON tenant_subscriptions (tenant_id)")
    op.execute("ALTER TABLE tenant_subscriptions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_subscriptions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON tenant_subscriptions USING (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE tenant_usage_counters (\n\tperiod VARCHAR NOT NULL, \n\tmetric VARCHAR NOT NULL, \n\tquantity INTEGER NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, period, metric), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_tenant_usage_counters_tenant_id ON tenant_usage_counters (tenant_id)"
    )
    op.execute("ALTER TABLE tenant_usage_counters ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_usage_counters FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON tenant_usage_counters USING (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE platform_operations (\n\tactor_id UUID NOT NULL, \n\ttenant_id UUID, \n\taction VARCHAR NOT NULL, \n\tdetails JSONB NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id)\n)\n\n"
    )
    op.execute(
        "CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON platform_operations FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )


def downgrade():
    raise RuntimeError(
        "Restore verified backup or use reviewed forward repair; operational history cannot be discarded"
    )
