"""Accounting facts, immutable lineage, analytics, connectors and sampling."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE background_jobs ADD COLUMN job_type VARCHAR NOT NULL DEFAULT 'diagnostic', ADD COLUMN progress INTEGER NOT NULL DEFAULT 0, ADD COLUMN payload JSONB NOT NULL DEFAULT '{}', ADD COLUMN result JSONB NOT NULL DEFAULT '{}'"
    )
    op.execute(
        "ALTER TABLE legal_entities ADD CONSTRAINT uq_entity_client_scope UNIQUE (tenant_id,client_id,id)"
    )
    op.execute(
        "ALTER TABLE financial_periods ADD CONSTRAINT uq_period_entity_scope UNIQUE (tenant_id,entity_id,id)"
    )
    op.execute(
        "\nCREATE TABLE audit_rules (\n\tcode VARCHAR NOT NULL, \n\tversion VARCHAR NOT NULL, \n\tdefinition JSONB NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, code, version), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_audit_rules_tenant_id ON audit_rules (tenant_id)")
    op.execute("ALTER TABLE audit_rules ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_rules FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_rules USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE currencies (\n\tcode VARCHAR NOT NULL, \n\tprecision INTEGER NOT NULL, \n\trounding VARCHAR NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, code), \n\tCHECK (precision BETWEEN 0 AND 8), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_currencies_tenant_id ON currencies (tenant_id)")
    op.execute("ALTER TABLE currencies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE currencies FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON currencies USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE account_mappings (\n\tname VARCHAR NOT NULL, \n\tversion INTEGER NOT NULL, \n\tmapping JSONB NOT NULL, \n\tapproved BOOLEAN NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tUNIQUE (tenant_id, entity_id, name, version), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_account_mappings_client_id ON account_mappings (client_id)")
    op.execute("CREATE INDEX ix_account_mappings_entity_id ON account_mappings (entity_id)")
    op.execute("CREATE INDEX ix_account_mappings_period_id ON account_mappings (period_id)")
    op.execute("CREATE INDEX ix_account_mappings_tenant_id ON account_mappings (tenant_id)")
    op.execute("ALTER TABLE account_mappings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE account_mappings FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON account_mappings USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE accounting_connections (\n\tprovider VARCHAR NOT NULL, \n\tname VARCHAR NOT NULL, \n\tregion VARCHAR NOT NULL, \n\torganization_id VARCHAR, \n\tencrypted_credentials TEXT, \n\tstatus VARCHAR NOT NULL, \n\tconfig JSONB NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_accounting_connections_client_id ON accounting_connections (client_id)"
    )
    op.execute(
        "CREATE INDEX ix_accounting_connections_entity_id ON accounting_connections (entity_id)"
    )
    op.execute(
        "CREATE INDEX ix_accounting_connections_period_id ON accounting_connections (period_id)"
    )
    op.execute(
        "CREATE INDEX ix_accounting_connections_tenant_id ON accounting_connections (tenant_id)"
    )
    op.execute("ALTER TABLE accounting_connections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE accounting_connections FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON accounting_connections USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE accounts (\n\tcode VARCHAR(100) NOT NULL, \n\tname VARCHAR(300) NOT NULL, \n\tclassification VARCHAR, \n\tstatement_group VARCHAR, \n\tsource_group VARCHAR, \n\tcontra BOOLEAN NOT NULL, \n\tparent_code VARCHAR, \n\tmapping_version INTEGER NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tUNIQUE (tenant_id, entity_id, code), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_accounts_client_id ON accounts (client_id)")
    op.execute("CREATE INDEX ix_accounts_entity_id ON accounts (entity_id)")
    op.execute("CREATE INDEX ix_accounts_period_id ON accounts (period_id)")
    op.execute("CREATE INDEX ix_accounts_tenant_id ON accounts (tenant_id)")
    op.execute("ALTER TABLE accounts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE accounts FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON accounts USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE exchange_rates (\n\tsource_currency VARCHAR NOT NULL, \n\ttarget_currency VARCHAR NOT NULL, \n\teffective_date DATE NOT NULL, \n\trate NUMERIC(28, 12) NOT NULL, \n\tsource VARCHAR NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tCHECK (rate > 0), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_exchange_rates_client_id ON exchange_rates (client_id)")
    op.execute("CREATE INDEX ix_exchange_rates_entity_id ON exchange_rates (entity_id)")
    op.execute("CREATE INDEX ix_exchange_rates_period_id ON exchange_rates (period_id)")
    op.execute("CREATE INDEX ix_exchange_rates_tenant_id ON exchange_rates (tenant_id)")
    op.execute("ALTER TABLE exchange_rates ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE exchange_rates FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON exchange_rates USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE import_batches (\n\tkind VARCHAR NOT NULL, \n\tsource_system VARCHAR NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tfingerprint VARCHAR NOT NULL, \n\toptions JSONB NOT NULL, \n\trow_count INTEGER NOT NULL, \n\tvalid_count INTEGER NOT NULL, \n\tprogress INTEGER NOT NULL, \n\tsupersedes_id UUID, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tUNIQUE (tenant_id, entity_id, period_id, kind, fingerprint), \n\tCHECK (progress BETWEEN 0 AND 100), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(supersedes_id) REFERENCES import_batches (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, supersedes_id) REFERENCES import_batches (tenant_id, id)\n)\n\n"
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_active_accounting_scope ON import_batches (tenant_id, entity_id, period_id, kind) WHERE status = 'active'"
    )
    op.execute("CREATE INDEX ix_import_batches_client_id ON import_batches (client_id)")
    op.execute("CREATE INDEX ix_import_batches_entity_id ON import_batches (entity_id)")
    op.execute("CREATE INDEX ix_import_batches_period_id ON import_batches (period_id)")
    op.execute("CREATE INDEX ix_import_batches_tenant_id ON import_batches (tenant_id)")
    op.execute("ALTER TABLE import_batches ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE import_batches FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON import_batches USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE connection_sync_runs (\n\tconnection_id UUID NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tcompleteness VARCHAR NOT NULL, \n\tmanifest JSONB NOT NULL, \n\terror_category VARCHAR, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(connection_id) REFERENCES accounting_connections (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, connection_id) REFERENCES accounting_connections (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_connection_sync_runs_client_id ON connection_sync_runs (client_id)")
    op.execute("CREATE INDEX ix_connection_sync_runs_entity_id ON connection_sync_runs (entity_id)")
    op.execute("CREATE INDEX ix_connection_sync_runs_period_id ON connection_sync_runs (period_id)")
    op.execute("CREATE INDEX ix_connection_sync_runs_tenant_id ON connection_sync_runs (tenant_id)")
    op.execute("ALTER TABLE connection_sync_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE connection_sync_runs FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON connection_sync_runs USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE data_transformations (\n\tbatch_id UUID NOT NULL, \n\tversion VARCHAR NOT NULL, \n\tdefinition JSONB NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(batch_id) REFERENCES import_batches (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, batch_id) REFERENCES import_batches (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_data_transformations_client_id ON data_transformations (client_id)")
    op.execute("CREATE INDEX ix_data_transformations_entity_id ON data_transformations (entity_id)")
    op.execute("CREATE INDEX ix_data_transformations_period_id ON data_transformations (period_id)")
    op.execute("CREATE INDEX ix_data_transformations_tenant_id ON data_transformations (tenant_id)")
    op.execute("ALTER TABLE data_transformations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE data_transformations FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON data_transformations USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE import_files (\n\tbatch_id UUID NOT NULL, \n\tfilename VARCHAR NOT NULL, \n\tobject_key VARCHAR NOT NULL, \n\tobject_version VARCHAR NOT NULL, \n\tsha256 VARCHAR NOT NULL, \n\tsize INTEGER NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tUNIQUE (batch_id), \n\tFOREIGN KEY(batch_id) REFERENCES import_batches (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, batch_id) REFERENCES import_batches (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_import_files_client_id ON import_files (client_id)")
    op.execute("CREATE INDEX ix_import_files_entity_id ON import_files (entity_id)")
    op.execute("CREATE INDEX ix_import_files_period_id ON import_files (period_id)")
    op.execute("CREATE INDEX ix_import_files_tenant_id ON import_files (tenant_id)")
    op.execute("ALTER TABLE import_files ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE import_files FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON import_files USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE import_validation_results (\n\tbatch_id UUID NOT NULL, \n\trow_number INTEGER, \n\trule VARCHAR NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tmessage VARCHAR NOT NULL, \n\tevidence JSONB NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(batch_id) REFERENCES import_batches (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, batch_id) REFERENCES import_batches (tenant_id, id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_import_validation_results_batch_id ON import_validation_results (batch_id)"
    )
    op.execute(
        "CREATE INDEX ix_import_validation_results_client_id ON import_validation_results (client_id)"
    )
    op.execute(
        "CREATE INDEX ix_import_validation_results_entity_id ON import_validation_results (entity_id)"
    )
    op.execute(
        "CREATE INDEX ix_import_validation_results_period_id ON import_validation_results (period_id)"
    )
    op.execute(
        "CREATE INDEX ix_import_validation_results_tenant_id ON import_validation_results (tenant_id)"
    )
    op.execute("ALTER TABLE import_validation_results ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE import_validation_results FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON import_validation_results USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE journal_entries (\n\tbatch_id UUID NOT NULL, \n\treference VARCHAR NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tUNIQUE (batch_id, reference), \n\tFOREIGN KEY(batch_id) REFERENCES import_batches (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, batch_id) REFERENCES import_batches (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_journal_entries_batch_id ON journal_entries (batch_id)")
    op.execute("CREATE INDEX ix_journal_entries_client_id ON journal_entries (client_id)")
    op.execute("CREATE INDEX ix_journal_entries_entity_id ON journal_entries (entity_id)")
    op.execute("CREATE INDEX ix_journal_entries_period_id ON journal_entries (period_id)")
    op.execute("CREATE INDEX ix_journal_entries_tenant_id ON journal_entries (tenant_id)")
    op.execute("ALTER TABLE journal_entries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE journal_entries FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON journal_entries USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE upload_sessions (\n\tfilename VARCHAR NOT NULL, \n\ttotal_size INTEGER NOT NULL, \n\tsha256 VARCHAR NOT NULL, \n\toptions JSONB NOT NULL, \n\tchunks JSONB NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tbatch_id UUID, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(batch_id) REFERENCES import_batches (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, batch_id) REFERENCES import_batches (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_upload_sessions_client_id ON upload_sessions (client_id)")
    op.execute("CREATE INDEX ix_upload_sessions_entity_id ON upload_sessions (entity_id)")
    op.execute("CREATE INDEX ix_upload_sessions_period_id ON upload_sessions (period_id)")
    op.execute("CREATE INDEX ix_upload_sessions_tenant_id ON upload_sessions (tenant_id)")
    op.execute("ALTER TABLE upload_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE upload_sessions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON upload_sessions USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE import_snapshots (\n\tbatch_id UUID NOT NULL, \n\tfile_id UUID NOT NULL, \n\tmanifest JSONB NOT NULL, \n\tsha256 VARCHAR NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tUNIQUE (batch_id), \n\tFOREIGN KEY(batch_id) REFERENCES import_batches (id), \n\tFOREIGN KEY(file_id) REFERENCES import_files (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, file_id) REFERENCES import_files (tenant_id, id), \n\tFOREIGN KEY(tenant_id, batch_id) REFERENCES import_batches (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_import_snapshots_client_id ON import_snapshots (client_id)")
    op.execute("CREATE INDEX ix_import_snapshots_entity_id ON import_snapshots (entity_id)")
    op.execute("CREATE INDEX ix_import_snapshots_period_id ON import_snapshots (period_id)")
    op.execute("CREATE INDEX ix_import_snapshots_tenant_id ON import_snapshots (tenant_id)")
    op.execute("ALTER TABLE import_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE import_snapshots FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON import_snapshots USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE audit_analytics_runs (\n\tsnapshot_id UUID NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tprogress INTEGER NOT NULL, \n\tparameters JSONB NOT NULL, \n\truleset_version VARCHAR NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(snapshot_id) REFERENCES import_snapshots (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, snapshot_id) REFERENCES import_snapshots (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_audit_analytics_runs_client_id ON audit_analytics_runs (client_id)")
    op.execute("CREATE INDEX ix_audit_analytics_runs_entity_id ON audit_analytics_runs (entity_id)")
    op.execute("CREATE INDEX ix_audit_analytics_runs_period_id ON audit_analytics_runs (period_id)")
    op.execute("CREATE INDEX ix_audit_analytics_runs_tenant_id ON audit_analytics_runs (tenant_id)")
    op.execute("ALTER TABLE audit_analytics_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_analytics_runs FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_analytics_runs USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE financial_ai_suggestions (\n\texecution_id UUID NOT NULL, \n\tsnapshot_id UUID NOT NULL, \n\ttask VARCHAR NOT NULL, \n\tsuggestion JSONB NOT NULL, \n\treview_status VARCHAR NOT NULL, \n\treviewed_by UUID, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(execution_id) REFERENCES ai_executions (id), \n\tFOREIGN KEY(snapshot_id) REFERENCES import_snapshots (id), \n\tFOREIGN KEY(reviewed_by) REFERENCES users (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, snapshot_id) REFERENCES import_snapshots (tenant_id, id), \n\tFOREIGN KEY(tenant_id, execution_id) REFERENCES ai_executions (tenant_id, id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_financial_ai_suggestions_client_id ON financial_ai_suggestions (client_id)"
    )
    op.execute(
        "CREATE INDEX ix_financial_ai_suggestions_entity_id ON financial_ai_suggestions (entity_id)"
    )
    op.execute(
        "CREATE INDEX ix_financial_ai_suggestions_period_id ON financial_ai_suggestions (period_id)"
    )
    op.execute(
        "CREATE INDEX ix_financial_ai_suggestions_tenant_id ON financial_ai_suggestions (tenant_id)"
    )
    op.execute("ALTER TABLE financial_ai_suggestions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE financial_ai_suggestions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON financial_ai_suggestions USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE reconciliation_runs (\n\tsnapshot_id UUID NOT NULL, \n\tcomparison_snapshot_id UUID, \n\tstatus VARCHAR NOT NULL, \n\tresult JSONB NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(snapshot_id) REFERENCES import_snapshots (id), \n\tFOREIGN KEY(comparison_snapshot_id) REFERENCES import_snapshots (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, comparison_snapshot_id) REFERENCES import_snapshots (tenant_id, id), \n\tFOREIGN KEY(tenant_id, snapshot_id) REFERENCES import_snapshots (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_reconciliation_runs_client_id ON reconciliation_runs (client_id)")
    op.execute("CREATE INDEX ix_reconciliation_runs_entity_id ON reconciliation_runs (entity_id)")
    op.execute("CREATE INDEX ix_reconciliation_runs_period_id ON reconciliation_runs (period_id)")
    op.execute("CREATE INDEX ix_reconciliation_runs_tenant_id ON reconciliation_runs (tenant_id)")
    op.execute("ALTER TABLE reconciliation_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE reconciliation_runs FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON reconciliation_runs USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE sampling_runs (\n\tsnapshot_id UUID NOT NULL, \n\tmethod VARCHAR NOT NULL, \n\tseed INTEGER NOT NULL, \n\tparameters JSONB NOT NULL, \n\tresult JSONB NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(snapshot_id) REFERENCES import_snapshots (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, snapshot_id) REFERENCES import_snapshots (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_sampling_runs_client_id ON sampling_runs (client_id)")
    op.execute("CREATE INDEX ix_sampling_runs_entity_id ON sampling_runs (entity_id)")
    op.execute("CREATE INDEX ix_sampling_runs_period_id ON sampling_runs (period_id)")
    op.execute("CREATE INDEX ix_sampling_runs_tenant_id ON sampling_runs (tenant_id)")
    op.execute("ALTER TABLE sampling_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sampling_runs FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON sampling_runs USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE source_integrity_checks (\n\tsnapshot_id UUID NOT NULL, \n\talgorithm VARCHAR NOT NULL, \n\texpected VARCHAR NOT NULL, \n\tobserved VARCHAR NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(snapshot_id) REFERENCES import_snapshots (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, snapshot_id) REFERENCES import_snapshots (tenant_id, id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_source_integrity_checks_client_id ON source_integrity_checks (client_id)"
    )
    op.execute(
        "CREATE INDEX ix_source_integrity_checks_entity_id ON source_integrity_checks (entity_id)"
    )
    op.execute(
        "CREATE INDEX ix_source_integrity_checks_period_id ON source_integrity_checks (period_id)"
    )
    op.execute(
        "CREATE INDEX ix_source_integrity_checks_tenant_id ON source_integrity_checks (tenant_id)"
    )
    op.execute("ALTER TABLE source_integrity_checks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE source_integrity_checks FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON source_integrity_checks USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE source_records (\n\tbatch_id UUID NOT NULL, \n\tsnapshot_id UUID NOT NULL, \n\trow_number INTEGER NOT NULL, \n\tsource_id VARCHAR NOT NULL, \n\tsha256 VARCHAR NOT NULL, \n\traw JSONB NOT NULL, \n\tcanonical JSONB, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tUNIQUE (batch_id, row_number), \n\tFOREIGN KEY(tenant_id, snapshot_id) REFERENCES import_snapshots (tenant_id, id), \n\tFOREIGN KEY(batch_id) REFERENCES import_batches (id), \n\tFOREIGN KEY(snapshot_id) REFERENCES import_snapshots (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(tenant_id, batch_id) REFERENCES import_batches (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_source_records_batch_id ON source_records (batch_id)")
    op.execute("CREATE INDEX ix_source_records_client_id ON source_records (client_id)")
    op.execute("CREATE INDEX ix_source_records_entity_id ON source_records (entity_id)")
    op.execute("CREATE INDEX ix_source_records_period_id ON source_records (period_id)")
    op.execute("CREATE INDEX ix_source_records_tenant_id ON source_records (tenant_id)")
    op.execute("ALTER TABLE source_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE source_records FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON source_records USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE trial_balance_snapshots (\n\tsnapshot_id UUID NOT NULL, \n\tcurrency VARCHAR NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tevidence JSONB NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(snapshot_id) REFERENCES import_snapshots (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, snapshot_id) REFERENCES import_snapshots (tenant_id, id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_trial_balance_snapshots_client_id ON trial_balance_snapshots (client_id)"
    )
    op.execute(
        "CREATE INDEX ix_trial_balance_snapshots_entity_id ON trial_balance_snapshots (entity_id)"
    )
    op.execute(
        "CREATE INDEX ix_trial_balance_snapshots_period_id ON trial_balance_snapshots (period_id)"
    )
    op.execute(
        "CREATE INDEX ix_trial_balance_snapshots_tenant_id ON trial_balance_snapshots (tenant_id)"
    )
    op.execute("ALTER TABLE trial_balance_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE trial_balance_snapshots FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON trial_balance_snapshots USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE audit_rule_results (\n\trun_id UUID NOT NULL, \n\trule_id VARCHAR NOT NULL, \n\trule_version VARCHAR NOT NULL, \n\tresult JSONB NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(run_id) REFERENCES audit_analytics_runs (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, run_id) REFERENCES audit_analytics_runs (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_audit_rule_results_client_id ON audit_rule_results (client_id)")
    op.execute("CREATE INDEX ix_audit_rule_results_entity_id ON audit_rule_results (entity_id)")
    op.execute("CREATE INDEX ix_audit_rule_results_period_id ON audit_rule_results (period_id)")
    op.execute("CREATE INDEX ix_audit_rule_results_run_id ON audit_rule_results (run_id)")
    op.execute("CREATE INDEX ix_audit_rule_results_tenant_id ON audit_rule_results (tenant_id)")
    op.execute("ALTER TABLE audit_rule_results ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_rule_results FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_rule_results USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE journal_lines (\n\tbatch_id UUID NOT NULL, \n\tsnapshot_id UUID NOT NULL, \n\tsource_record_id UUID NOT NULL, \n\tjournal_id UUID NOT NULL, \n\taccount_id UUID NOT NULL, \n\tposting_date DATE NOT NULL, \n\tdocument_date DATE, \n\tdebit NUMERIC(28, 8) NOT NULL, \n\tcredit NUMERIC(28, 8) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\tfunctional_currency VARCHAR(3) NOT NULL, \n\texchange_rate NUMERIC(28, 12) NOT NULL, \n\tbase_debit NUMERIC(28, 8) NOT NULL, \n\tbase_credit NUMERIC(28, 8) NOT NULL, \n\topening BOOLEAN NOT NULL, \n\tdescription TEXT NOT NULL, \n\tcounterparty VARCHAR, \n\tattributes JSONB NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tCHECK (debit >= 0 AND credit >= 0 AND NOT (debit > 0 AND credit > 0)), \n\tFOREIGN KEY(tenant_id, journal_id) REFERENCES journal_entries (tenant_id, id), \n\tFOREIGN KEY(tenant_id, account_id) REFERENCES accounts (tenant_id, id), \n\tFOREIGN KEY(tenant_id, source_record_id) REFERENCES source_records (tenant_id, id), \n\tFOREIGN KEY(batch_id) REFERENCES import_batches (id), \n\tFOREIGN KEY(snapshot_id) REFERENCES import_snapshots (id), \n\tUNIQUE (source_record_id), \n\tFOREIGN KEY(source_record_id) REFERENCES source_records (id), \n\tFOREIGN KEY(journal_id) REFERENCES journal_entries (id), \n\tFOREIGN KEY(account_id) REFERENCES accounts (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(tenant_id, snapshot_id) REFERENCES import_snapshots (tenant_id, id), \n\tFOREIGN KEY(tenant_id, batch_id) REFERENCES import_batches (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_journal_lines_account_id ON journal_lines (account_id)")
    op.execute("CREATE INDEX ix_journal_lines_batch_id ON journal_lines (batch_id)")
    op.execute("CREATE INDEX ix_journal_lines_client_id ON journal_lines (client_id)")
    op.execute("CREATE INDEX ix_journal_lines_entity_id ON journal_lines (entity_id)")
    op.execute("CREATE INDEX ix_journal_lines_journal_id ON journal_lines (journal_id)")
    op.execute("CREATE INDEX ix_journal_lines_period_id ON journal_lines (period_id)")
    op.execute("CREATE INDEX ix_journal_lines_posting_date ON journal_lines (posting_date)")
    op.execute("CREATE INDEX ix_journal_lines_tenant_id ON journal_lines (tenant_id)")
    op.execute(
        "CREATE INDEX ix_lines_scope_account_date ON journal_lines (tenant_id, entity_id, period_id, account_id, posting_date)"
    )
    op.execute("ALTER TABLE journal_lines ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE journal_lines FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON journal_lines USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE reconciliation_exceptions (\n\trun_id UUID NOT NULL, \n\taccount_code VARCHAR, \n\tdetails JSONB NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(run_id) REFERENCES reconciliation_runs (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, run_id) REFERENCES reconciliation_runs (tenant_id, id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_reconciliation_exceptions_client_id ON reconciliation_exceptions (client_id)"
    )
    op.execute(
        "CREATE INDEX ix_reconciliation_exceptions_entity_id ON reconciliation_exceptions (entity_id)"
    )
    op.execute(
        "CREATE INDEX ix_reconciliation_exceptions_period_id ON reconciliation_exceptions (period_id)"
    )
    op.execute(
        "CREATE INDEX ix_reconciliation_exceptions_run_id ON reconciliation_exceptions (run_id)"
    )
    op.execute(
        "CREATE INDEX ix_reconciliation_exceptions_tenant_id ON reconciliation_exceptions (tenant_id)"
    )
    op.execute("ALTER TABLE reconciliation_exceptions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE reconciliation_exceptions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON reconciliation_exceptions USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE trial_balance_lines (\n\ttrial_balance_id UUID NOT NULL, \n\taccount_id UUID NOT NULL, \n\topening NUMERIC(28, 8) NOT NULL, \n\tdebit NUMERIC(28, 8) NOT NULL, \n\tcredit NUMERIC(28, 8) NOT NULL, \n\tclosing NUMERIC(28, 8) NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tCHECK (closing = opening + debit - credit), \n\tFOREIGN KEY(trial_balance_id) REFERENCES trial_balance_snapshots (id), \n\tFOREIGN KEY(account_id) REFERENCES accounts (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, account_id) REFERENCES accounts (tenant_id, id), \n\tFOREIGN KEY(tenant_id, trial_balance_id) REFERENCES trial_balance_snapshots (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_trial_balance_lines_client_id ON trial_balance_lines (client_id)")
    op.execute("CREATE INDEX ix_trial_balance_lines_entity_id ON trial_balance_lines (entity_id)")
    op.execute("CREATE INDEX ix_trial_balance_lines_period_id ON trial_balance_lines (period_id)")
    op.execute("CREATE INDEX ix_trial_balance_lines_tenant_id ON trial_balance_lines (tenant_id)")
    op.execute(
        "CREATE INDEX ix_trial_balance_lines_trial_balance_id ON trial_balance_lines (trial_balance_id)"
    )
    op.execute("ALTER TABLE trial_balance_lines ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE trial_balance_lines FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON trial_balance_lines USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE audit_findings (\n\trun_id UUID NOT NULL, \n\tline_id UUID, \n\trule_id VARCHAR NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tevidence JSONB NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(run_id) REFERENCES audit_analytics_runs (id), \n\tFOREIGN KEY(line_id) REFERENCES journal_lines (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, line_id) REFERENCES journal_lines (tenant_id, id), \n\tFOREIGN KEY(tenant_id, run_id) REFERENCES audit_analytics_runs (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_audit_findings_client_id ON audit_findings (client_id)")
    op.execute("CREATE INDEX ix_audit_findings_entity_id ON audit_findings (entity_id)")
    op.execute("CREATE INDEX ix_audit_findings_period_id ON audit_findings (period_id)")
    op.execute("CREATE INDEX ix_audit_findings_run_id ON audit_findings (run_id)")
    op.execute("CREATE INDEX ix_audit_findings_tenant_id ON audit_findings (tenant_id)")
    op.execute("ALTER TABLE audit_findings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_findings FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_findings USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE risk_scores (\n\trun_id UUID NOT NULL, \n\tline_id UUID NOT NULL, \n\tscore NUMERIC(6, 3) NOT NULL, \n\tband VARCHAR NOT NULL, \n\tfactors JSONB NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tCHECK (score BETWEEN 0 AND 100), \n\tFOREIGN KEY(run_id) REFERENCES audit_analytics_runs (id), \n\tFOREIGN KEY(line_id) REFERENCES journal_lines (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, line_id) REFERENCES journal_lines (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, run_id) REFERENCES audit_analytics_runs (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_risk_scores_client_id ON risk_scores (client_id)")
    op.execute("CREATE INDEX ix_risk_scores_entity_id ON risk_scores (entity_id)")
    op.execute("CREATE INDEX ix_risk_scores_period_id ON risk_scores (period_id)")
    op.execute("CREATE INDEX ix_risk_scores_run_id ON risk_scores (run_id)")
    op.execute("CREATE INDEX ix_risk_scores_tenant_id ON risk_scores (tenant_id)")
    op.execute("ALTER TABLE risk_scores ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE risk_scores FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON risk_scores USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE sampling_items (\n\trun_id UUID NOT NULL, \n\tline_id UUID NOT NULL, \n\thits INTEGER NOT NULL, \n\tclient_id UUID NOT NULL, \n\tentity_id UUID NOT NULL, \n\tperiod_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tUNIQUE (run_id, line_id), \n\tFOREIGN KEY(run_id) REFERENCES sampling_runs (id), \n\tFOREIGN KEY(line_id) REFERENCES journal_lines (id), \n\tFOREIGN KEY(client_id) REFERENCES clients (id), \n\tFOREIGN KEY(entity_id) REFERENCES legal_entities (id), \n\tFOREIGN KEY(period_id) REFERENCES financial_periods (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id, client_id, entity_id) REFERENCES legal_entities (tenant_id, client_id, id), \n\tFOREIGN KEY(tenant_id, entity_id, period_id) REFERENCES financial_periods (tenant_id, entity_id, id), \n\tFOREIGN KEY(tenant_id, run_id) REFERENCES sampling_runs (tenant_id, id), \n\tFOREIGN KEY(tenant_id, entity_id) REFERENCES legal_entities (tenant_id, id), \n\tFOREIGN KEY(tenant_id, line_id) REFERENCES journal_lines (tenant_id, id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, period_id) REFERENCES financial_periods (tenant_id, id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_sampling_items_client_id ON sampling_items (client_id)")
    op.execute("CREATE INDEX ix_sampling_items_entity_id ON sampling_items (entity_id)")
    op.execute("CREATE INDEX ix_sampling_items_period_id ON sampling_items (period_id)")
    op.execute("CREATE INDEX ix_sampling_items_run_id ON sampling_items (run_id)")
    op.execute("CREATE INDEX ix_sampling_items_tenant_id ON sampling_items (tenant_id)")
    op.execute("ALTER TABLE sampling_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sampling_items FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON sampling_items USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "CREATE TRIGGER immutable_import_files BEFORE UPDATE OR DELETE ON import_files FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "CREATE TRIGGER immutable_import_snapshots BEFORE UPDATE OR DELETE ON import_snapshots FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "CREATE TRIGGER immutable_source_records BEFORE UPDATE OR DELETE ON source_records FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "CREATE TRIGGER immutable_data_transformations BEFORE UPDATE OR DELETE ON data_transformations FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "CREATE TRIGGER immutable_journal_entries BEFORE UPDATE OR DELETE ON journal_entries FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "CREATE TRIGGER immutable_journal_lines BEFORE UPDATE OR DELETE ON journal_lines FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "CREATE TRIGGER immutable_trial_balance_snapshots BEFORE UPDATE OR DELETE ON trial_balance_snapshots FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "CREATE TRIGGER immutable_trial_balance_lines BEFORE UPDATE OR DELETE ON trial_balance_lines FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "CREATE TRIGGER immutable_audit_rule_results BEFORE UPDATE OR DELETE ON audit_rule_results FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "CREATE TRIGGER immutable_sampling_items BEFORE UPDATE OR DELETE ON sampling_items FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "CREATE TRIGGER immutable_source_integrity_checks BEFORE UPDATE OR DELETE ON source_integrity_checks FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "CREATE VIEW general_ledger_transactions WITH (security_invoker=true) AS SELECT l.*, (l.base_debit-l.base_credit) AS signed_amount FROM journal_lines l JOIN import_batches b ON b.id=l.batch_id WHERE b.status='active'"
    )
    op.execute(
        "CREATE VIEW accounting_period_balances WITH (security_invoker=true) AS SELECT tenant_id,entity_id,period_id,account_id,functional_currency,SUM(CASE WHEN opening THEN base_debit-base_credit ELSE 0 END) AS opening_balance,SUM(CASE WHEN NOT opening THEN base_debit ELSE 0 END) AS debit,SUM(CASE WHEN NOT opening THEN base_credit ELSE 0 END) AS credit,SUM(base_debit-base_credit) AS closing_balance FROM general_ledger_transactions GROUP BY tenant_id,entity_id,period_id,account_id,functional_currency"
    )
    op.execute(
        "CREATE VIEW source_record_versions WITH (security_invoker=true) AS SELECT id,tenant_id,batch_id,snapshot_id,source_id,sha256,row_number,created_at FROM source_records"
    )
    op.execute(
        "CREATE VIEW record_lineage WITH (security_invoker=true) AS SELECT l.tenant_id,l.client_id,l.entity_id,l.period_id,l.id AS journal_line_id,l.journal_id,s.id AS source_record_id,s.source_id,s.snapshot_id,s.batch_id,f.object_key,f.object_version,f.sha256 FROM journal_lines l JOIN source_records s ON s.id=l.source_record_id JOIN import_snapshots snap ON snap.id=s.snapshot_id JOIN import_files f ON f.id=snap.file_id"
    )
    op.execute(
        "INSERT INTO permissions (id,code) VALUES (gen_random_uuid(),'accounting.read') ON CONFLICT (code) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id,permission_id) SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.name='Firm Administrator' AND p.code='accounting.read' ON CONFLICT DO NOTHING"
    )
    op.execute(
        "INSERT INTO permissions (id,code) VALUES (gen_random_uuid(),'accounting.import') ON CONFLICT (code) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id,permission_id) SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.name='Firm Administrator' AND p.code='accounting.import' ON CONFLICT DO NOTHING"
    )
    op.execute(
        "INSERT INTO permissions (id,code) VALUES (gen_random_uuid(),'accounting.map') ON CONFLICT (code) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id,permission_id) SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.name='Firm Administrator' AND p.code='accounting.map' ON CONFLICT DO NOTHING"
    )
    op.execute(
        "INSERT INTO permissions (id,code) VALUES (gen_random_uuid(),'connectors.manage') ON CONFLICT (code) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id,permission_id) SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.name='Firm Administrator' AND p.code='connectors.manage' ON CONFLICT DO NOTHING"
    )
    op.execute(
        "INSERT INTO permissions (id,code) VALUES (gen_random_uuid(),'analytics.run') ON CONFLICT (code) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id,permission_id) SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.name='Firm Administrator' AND p.code='analytics.run' ON CONFLICT DO NOTHING"
    )
    op.execute(
        "INSERT INTO permissions (id,code) VALUES (gen_random_uuid(),'analytics.read') ON CONFLICT (code) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id,permission_id) SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.name='Firm Administrator' AND p.code='analytics.read' ON CONFLICT DO NOTHING"
    )
    op.execute(
        "INSERT INTO permissions (id,code) VALUES (gen_random_uuid(),'sampling.run') ON CONFLICT (code) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id,permission_id) SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.name='Firm Administrator' AND p.code='sampling.run' ON CONFLICT DO NOTHING"
    )
    op.execute(
        "INSERT INTO permissions (id,code) VALUES (gen_random_uuid(),'financial_ai.execute') ON CONFLICT (code) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id,permission_id) SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.name='Firm Administrator' AND p.code='financial_ai.execute' ON CONFLICT DO NOTHING"
    )
    op.execute(
        "INSERT INTO permissions (id,code) VALUES (gen_random_uuid(),'financial_ai.approve') ON CONFLICT (code) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id,permission_id) SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.name='Firm Administrator' AND p.code='financial_ai.approve' ON CONFLICT DO NOTHING"
    )
    op.execute(
        "INSERT INTO ai_prompt_templates (id,name,version,content) VALUES (gen_random_uuid(),'account_classification',1,'Use only supplied evidence; cite supplied record IDs. Do not calculate financial results, infer causation or execute tools. Return the requested JSON schema as a suggestion requiring human review. Unknown causes require investigation.') ON CONFLICT (name,version) DO NOTHING"
    )
    op.execute(
        "INSERT INTO ai_prompt_templates (id,name,version,content) VALUES (gen_random_uuid(),'anomaly_explanation',1,'Use only supplied evidence; cite supplied record IDs. Do not calculate financial results, infer causation or execute tools. Return the requested JSON schema as a suggestion requiring human review. Unknown causes require investigation.') ON CONFLICT (name,version) DO NOTHING"
    )
    op.execute(
        "INSERT INTO ai_prompt_templates (id,name,version,content) VALUES (gen_random_uuid(),'audit_procedures',1,'Use only supplied evidence; cite supplied record IDs. Do not calculate financial results, infer causation or execute tools. Return the requested JSON schema as a suggestion requiring human review. Unknown causes require investigation.') ON CONFLICT (name,version) DO NOTHING"
    )
    op.execute(
        "INSERT INTO ai_prompt_templates (id,name,version,content) VALUES (gen_random_uuid(),'financial_commentary',1,'Use only supplied evidence; cite supplied record IDs. Do not calculate financial results, infer causation or execute tools. Return the requested JSON schema as a suggestion requiring human review. Unknown causes require investigation.') ON CONFLICT (name,version) DO NOTHING"
    )

    op.execute(
        "ALTER TABLE accounts ADD COLUMN mapping_profile_id UUID REFERENCES account_mappings(id)"
    )
    op.execute(
        "ALTER TABLE accounts ADD FOREIGN KEY (tenant_id,mapping_profile_id) REFERENCES account_mappings(tenant_id,id)"
    )


def downgrade():
    op.execute(
        "ALTER TABLE background_jobs DROP COLUMN job_type, DROP COLUMN progress, DROP COLUMN payload, DROP COLUMN result"
    )
    op.execute("DROP VIEW record_lineage")
    op.execute("DROP VIEW source_record_versions")
    op.execute("DROP VIEW accounting_period_balances")
    op.execute("DROP VIEW general_ledger_transactions")
    op.drop_table("sampling_items")
    op.drop_table("risk_scores")
    op.drop_table("audit_findings")
    op.drop_table("trial_balance_lines")
    op.drop_table("reconciliation_exceptions")
    op.drop_table("journal_lines")
    op.drop_table("audit_rule_results")
    op.drop_table("trial_balance_snapshots")
    op.drop_table("source_records")
    op.drop_table("source_integrity_checks")
    op.drop_table("sampling_runs")
    op.drop_table("reconciliation_runs")
    op.drop_table("financial_ai_suggestions")
    op.drop_table("audit_analytics_runs")
    op.drop_table("import_snapshots")
    op.drop_table("upload_sessions")
    op.drop_table("journal_entries")
    op.drop_table("import_validation_results")
    op.drop_table("import_files")
    op.drop_table("data_transformations")
    op.drop_table("connection_sync_runs")
    op.drop_table("import_batches")
    op.drop_table("exchange_rates")
    op.drop_table("accounts")
    op.drop_table("accounting_connections")
    op.drop_table("account_mappings")
    op.drop_table("currencies")
    op.drop_table("audit_rules")
    op.drop_constraint("uq_period_entity_scope", "financial_periods", type_="unique")
    op.drop_constraint("uq_entity_client_scope", "legal_entities", type_="unique")
    # Retain prompt/permission catalogue rows referenced by historical Phase 1 AI executions.
