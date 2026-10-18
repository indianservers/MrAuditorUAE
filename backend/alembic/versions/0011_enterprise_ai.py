"""Enterprise AI durable state; frozen schema and permission grants."""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "\nCREATE TABLE ai_workflow_runs (\n\tidempotency_key VARCHAR NOT NULL, \n\ttask VARCHAR NOT NULL, \n\tprompt VARCHAR NOT NULL, \n\tstate VARCHAR NOT NULL, \n\tplan JSONB NOT NULL, \n\tinputs JSONB NOT NULL, \n\toutputs JSONB NOT NULL, \n\tversion INTEGER NOT NULL, \n\tengagement_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tUNIQUE (tenant_id, created_by, idempotency_key), \n\tFOREIGN KEY(tenant_id, engagement_id) REFERENCES engagements (tenant_id, id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_ai_workflow_runs_tenant_id ON ai_workflow_runs (tenant_id)")
    op.execute("CREATE INDEX ix_ai_workflow_runs_state ON ai_workflow_runs (state)")
    op.execute("CREATE INDEX ix_ai_workflow_runs_engagement_id ON ai_workflow_runs (engagement_id)")
    op.execute("ALTER TABLE ai_workflow_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_workflow_runs FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON ai_workflow_runs USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE ai_workflow_events (\n\trun_id UUID NOT NULL, \n\tkey VARCHAR NOT NULL, \n\tkind VARCHAR NOT NULL, \n\tbody JSONB NOT NULL, \n\tsha256 VARCHAR NOT NULL, \n\tengagement_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tUNIQUE (run_id, key), \n\tFOREIGN KEY(tenant_id, run_id) REFERENCES ai_workflow_runs (tenant_id, id), \n\tFOREIGN KEY(tenant_id, engagement_id) REFERENCES engagements (tenant_id, id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_ai_workflow_events_tenant_id ON ai_workflow_events (tenant_id)")
    op.execute(
        "CREATE INDEX ix_ai_workflow_events_engagement_id ON ai_workflow_events (engagement_id)"
    )
    op.execute("ALTER TABLE ai_workflow_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_workflow_events FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON ai_workflow_events USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON ai_workflow_events FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "\nCREATE TABLE ai_document_extractions (\n\trecord_id UUID NOT NULL, \n\tevidence_version_id UUID NOT NULL, \n\trecord_version INTEGER NOT NULL, \n\tparent_id UUID, \n\tsource_hash VARCHAR NOT NULL, \n\tclassification VARCHAR NOT NULL, \n\tconfidentiality VARCHAR NOT NULL, \n\tbody JSONB NOT NULL, \n\tengagement_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, record_id) REFERENCES audit_records (tenant_id, id), \n\tFOREIGN KEY(tenant_id, engagement_id) REFERENCES engagements (tenant_id, id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_ai_document_extractions_tenant_id ON ai_document_extractions (tenant_id)"
    )
    op.execute(
        "CREATE INDEX ix_ai_document_extractions_engagement_id ON ai_document_extractions (engagement_id)"
    )
    op.execute("ALTER TABLE ai_document_extractions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_document_extractions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON ai_document_extractions USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON ai_document_extractions FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "\nCREATE TABLE ai_document_chunks (\n\textraction_id UUID NOT NULL, \n\tpage INTEGER NOT NULL, \n\tsection VARCHAR NOT NULL, \n\ttext VARCHAR NOT NULL, \n\tmetadata_details JSONB NOT NULL, \n\tengagement_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, extraction_id) REFERENCES ai_document_extractions (tenant_id, id), \n\tFOREIGN KEY(tenant_id, engagement_id) REFERENCES engagements (tenant_id, id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_ai_document_chunks_extraction_id ON ai_document_chunks (extraction_id)"
    )
    op.execute(
        "CREATE INDEX ix_ai_document_chunks_engagement_id ON ai_document_chunks (engagement_id)"
    )
    op.execute("CREATE INDEX ix_ai_document_chunks_tenant_id ON ai_document_chunks (tenant_id)")
    op.execute("ALTER TABLE ai_document_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_document_chunks FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON ai_document_chunks USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON ai_document_chunks FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "\nCREATE TABLE ai_approval_requests (\n\trun_id UUID NOT NULL, \n\taction VARCHAR NOT NULL, \n\tpayload JSONB NOT NULL, \n\tdependencies JSONB NOT NULL, \n\tpayload_hash VARCHAR NOT NULL, \n\tstate VARCHAR NOT NULL, \n\tdecision JSONB NOT NULL, \n\tresult JSONB NOT NULL, \n\tversion INTEGER NOT NULL, \n\tengagement_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, run_id) REFERENCES ai_workflow_runs (tenant_id, id), \n\tFOREIGN KEY(tenant_id, engagement_id) REFERENCES engagements (tenant_id, id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_ai_approval_requests_tenant_id ON ai_approval_requests (tenant_id)")
    op.execute(
        "CREATE INDEX ix_ai_approval_requests_engagement_id ON ai_approval_requests (engagement_id)"
    )
    op.execute("ALTER TABLE ai_approval_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_approval_requests FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON ai_approval_requests USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE ai_scheduled_workflows (\n\ttask VARCHAR NOT NULL, \n\tfrequency VARCHAR NOT NULL, \n\tactive BOOLEAN NOT NULL, \n\tnext_due TIMESTAMP WITH TIME ZONE NOT NULL, \n\tinputs JSONB NOT NULL, \n\tversion INTEGER NOT NULL, \n\tengagement_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tFOREIGN KEY(tenant_id, engagement_id) REFERENCES engagements (tenant_id, id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_ai_scheduled_workflows_engagement_id ON ai_scheduled_workflows (engagement_id)"
    )
    op.execute(
        "CREATE INDEX ix_ai_scheduled_workflows_next_due ON ai_scheduled_workflows (next_due)"
    )
    op.execute(
        "CREATE INDEX ix_ai_scheduled_workflows_tenant_id ON ai_scheduled_workflows (tenant_id)"
    )
    op.execute("ALTER TABLE ai_scheduled_workflows ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_scheduled_workflows FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON ai_scheduled_workflows USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE ai_document_match_decisions (\n\textraction_id UUID NOT NULL, \n\tjournal_id UUID NOT NULL, \n\tpayload_hash VARCHAR NOT NULL, \n\tbody JSONB NOT NULL, \n\tengagement_id UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, id), \n\tUNIQUE (tenant_id, created_by, payload_hash), \n\tFOREIGN KEY(tenant_id, engagement_id) REFERENCES engagements (tenant_id, id), \n\tFOREIGN KEY(tenant_id, extraction_id) REFERENCES ai_document_extractions (tenant_id, id), \n\tFOREIGN KEY(tenant_id, journal_id) REFERENCES journal_lines (tenant_id, id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_ai_document_match_decisions_engagement_id ON ai_document_match_decisions (engagement_id)"
    )
    op.execute(
        "CREATE INDEX ix_ai_document_match_decisions_tenant_id ON ai_document_match_decisions (tenant_id)"
    )
    op.execute("ALTER TABLE ai_document_match_decisions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_document_match_decisions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON ai_document_match_decisions USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON ai_document_match_decisions FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    grants = {
        "Platform Administrator": [],
        "Firm Administrator": [
            "ai.agent.configure",
            "ai.approval.decide",
            "ai.approval.request",
            "ai.auditlog.read",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.knowledge.manage",
            "ai.model.evaluate",
            "ai.provider.manage",
            "ai.tools.manage",
            "ai.usage.read",
            "ai.workflow.run",
            "ai.workflow.schedule",
        ],
        "Audit Partner": [
            "ai.approval.decide",
            "ai.approval.request",
            "ai.auditlog.read",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.knowledge.manage",
            "ai.model.evaluate",
            "ai.usage.read",
            "ai.workflow.run",
            "ai.workflow.schedule",
        ],
        "Audit Manager": [
            "ai.approval.decide",
            "ai.approval.request",
            "ai.auditlog.read",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.knowledge.manage",
            "ai.model.evaluate",
            "ai.usage.read",
            "ai.workflow.run",
            "ai.workflow.schedule",
        ],
        "Senior Auditor": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Auditor": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Tax Manager": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Tax Consultant": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Client Viewer": [],
        "Managing Partner": [
            "ai.approval.decide",
            "ai.approval.request",
            "ai.auditlog.read",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.knowledge.manage",
            "ai.model.evaluate",
            "ai.usage.read",
            "ai.workflow.run",
            "ai.workflow.schedule",
        ],
        "Audit Partner / Chartered Accountant": [
            "ai.approval.decide",
            "ai.approval.request",
            "ai.auditlog.read",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.knowledge.manage",
            "ai.model.evaluate",
            "ai.usage.read",
            "ai.workflow.run",
            "ai.workflow.schedule",
        ],
        "Audit Trainee": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Quality Reviewer": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Read-only Reviewer": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Firm Operations User": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Platform Super Admin": [],
        "Platform Support Administrator": [],
        "Client Administrator": [],
        "Client Finance Manager": [],
        "Client Accountant": [],
        "Client Document Contributor": [],
        "Financial Reporting Preparer": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Financial Reporting Manager": [
            "ai.approval.decide",
            "ai.approval.request",
            "ai.auditlog.read",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.knowledge.manage",
            "ai.model.evaluate",
            "ai.usage.read",
            "ai.workflow.run",
            "ai.workflow.schedule",
        ],
        "Chartered Accountant": [
            "ai.approval.decide",
            "ai.approval.request",
            "ai.auditlog.read",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.knowledge.manage",
            "ai.model.evaluate",
            "ai.usage.read",
            "ai.workflow.run",
            "ai.workflow.schedule",
        ],
        "Consolidation Specialist": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Corporate Tax Preparer": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Senior Tax Consultant": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Tax Director": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Tax Partner": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Independent Reviewer": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Client Finance User": [],
        "VAT Analyst": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "VAT Consultant": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Invoice Validator": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "VAT Manager": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "VAT Read-only Reviewer": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "TP Analyst": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "TP Economist": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Financial Analyst": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "TP Manager": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Transfer Pricing Director": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "TP Read-only Reviewer": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "ML Engineer": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Model Risk Reviewer": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Pillar Two Analyst": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Pillar Two Reviewer": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Chief Audit Executive": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Head of Internal Audit": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Internal Audit Manager": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Senior Internal Auditor": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Internal Auditor": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Risk Manager": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Compliance Officer": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "Risk Owner": [],
        "Control Owner": [],
        "Process Owner": [],
        "Remediation Owner": [],
        "Audit Committee Member": [],
        "Board Viewer": [],
        "Internal Audit Quality Reviewer": [
            "ai.approval.request",
            "ai.chat.use",
            "ai.documents.index",
            "ai.investigation.create",
            "ai.investigation.read",
            "ai.workflow.run",
        ],
        "AI Administrator": [
            "ai.agent.configure",
            "ai.auditlog.read",
            "ai.model.evaluate",
            "ai.provider.manage",
            "ai.tools.manage",
            "ai.usage.read",
        ],
    }
    connection = op.get_bind()
    for role_name, codes in grants.items():
        rid = connection.execute(
            sa.text("SELECT id FROM roles WHERE name=:name"), {"name": role_name}
        ).scalar()
        if rid is None:
            rid = uuid.uuid4()
            connection.execute(
                sa.text("INSERT INTO roles(id,name) VALUES(:id,:name)"),
                {"id": rid, "name": role_name},
            )
        for code in codes:
            pid = connection.execute(
                sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}
            ).scalar()
            if pid is None:
                pid = uuid.uuid4()
                connection.execute(
                    sa.text("INSERT INTO permissions(id,code) VALUES(:id,:code)"),
                    {"id": pid, "code": code},
                )
            connection.execute(
                sa.text(
                    "INSERT INTO role_permissions(role_id,permission_id) VALUES(:rid,:pid) ON CONFLICT DO NOTHING"
                ),
                {"rid": rid, "pid": pid},
            )


def downgrade():
    raise RuntimeError("Enterprise AI history requires an explicit reviewed archival migration")
