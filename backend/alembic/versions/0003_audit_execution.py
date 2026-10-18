"""Engagement audit records, scoped roles and immutable review history."""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "\nCREATE TABLE audit_invitations (\n\temail VARCHAR NOT NULL, \n\ttoken_hash VARCHAR NOT NULL, \n\trole_ids JSONB NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tused BOOLEAN NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (token_hash), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_audit_invitations_tenant_id ON audit_invitations (tenant_id)")
    op.execute("ALTER TABLE audit_invitations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_invitations FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_invitations USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE audit_role_policies (\n\trole_id UUID NOT NULL, \n\tpermissions JSONB NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (tenant_id, role_id), \n\tFOREIGN KEY(role_id) REFERENCES roles (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_audit_role_policies_tenant_id ON audit_role_policies (tenant_id)")
    op.execute("ALTER TABLE audit_role_policies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_role_policies FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_role_policies USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE audit_client_access (\n\tclient_id UUID NOT NULL, \n\tmembership_id UUID NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(tenant_id, client_id) REFERENCES clients (tenant_id, id), \n\tFOREIGN KEY(tenant_id, membership_id) REFERENCES tenant_memberships (tenant_id, id), \n\tUNIQUE (tenant_id, client_id, membership_id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_audit_client_access_tenant_id ON audit_client_access (tenant_id)")
    op.execute("ALTER TABLE audit_client_access ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_client_access FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_client_access USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE audit_access_grants (\n\tengagement_id UUID NOT NULL, \n\tmembership_id UUID NOT NULL, \n\trole_id UUID NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE, \n\tactive BOOLEAN NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(tenant_id, engagement_id) REFERENCES engagements (tenant_id, id), \n\tFOREIGN KEY(tenant_id, membership_id) REFERENCES tenant_memberships (tenant_id, id), \n\tUNIQUE (engagement_id, membership_id, role_id), \n\tFOREIGN KEY(role_id) REFERENCES roles (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_audit_access_grants_tenant_id ON audit_access_grants (tenant_id)")
    op.execute("ALTER TABLE audit_access_grants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_access_grants FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_access_grants USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE audit_engagement_policies (\n\tengagement_id UUID NOT NULL, \n\tquality_review_required BOOLEAN NOT NULL, \n\treview_chain JSONB NOT NULL, \n\tmethodology JSONB NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(tenant_id, engagement_id) REFERENCES engagements (tenant_id, id), \n\tUNIQUE (tenant_id, engagement_id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_audit_engagement_policies_tenant_id ON audit_engagement_policies (tenant_id)"
    )
    op.execute("ALTER TABLE audit_engagement_policies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_engagement_policies FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_engagement_policies USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE audit_records (\n\tengagement_id UUID NOT NULL, \n\tkind VARCHAR NOT NULL, \n\treference VARCHAR NOT NULL, \n\ttitle VARCHAR NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tbody JSONB NOT NULL, \n\tversion INTEGER NOT NULL, \n\tprepared_by UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(tenant_id, engagement_id) REFERENCES engagements (tenant_id, id), \n\tUNIQUE (tenant_id, id), \n\tUNIQUE (engagement_id, kind, reference), \n\tFOREIGN KEY(prepared_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_audit_records_engagement_id ON audit_records (engagement_id)")
    op.execute("CREATE INDEX ix_audit_records_status ON audit_records (status)")
    op.execute("CREATE INDEX ix_audit_records_kind ON audit_records (kind)")
    op.execute("CREATE INDEX ix_audit_records_tenant_id ON audit_records (tenant_id)")
    op.execute("ALTER TABLE audit_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_records FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_records USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE audit_evidence_versions (\n\trecord_id UUID NOT NULL, \n\tnumber INTEGER NOT NULL, \n\tfilename VARCHAR NOT NULL, \n\tmedia_type VARCHAR NOT NULL, \n\tobject_key VARCHAR NOT NULL, \n\tobject_version VARCHAR NOT NULL, \n\tsha256 VARCHAR NOT NULL, \n\tsize INTEGER NOT NULL, \n\tscan_status VARCHAR NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(tenant_id, record_id) REFERENCES audit_records (tenant_id, id), \n\tUNIQUE (record_id, number), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_audit_evidence_versions_tenant_id ON audit_evidence_versions (tenant_id)"
    )
    op.execute("ALTER TABLE audit_evidence_versions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_evidence_versions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_evidence_versions USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE audit_record_versions (\n\trecord_id UUID NOT NULL, \n\tversion INTEGER NOT NULL, \n\tsnapshot JSONB NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(tenant_id, record_id) REFERENCES audit_records (tenant_id, id), \n\tUNIQUE (record_id, version), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_audit_record_versions_tenant_id ON audit_record_versions (tenant_id)"
    )
    op.execute("ALTER TABLE audit_record_versions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_record_versions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_record_versions USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "\nCREATE TABLE audit_review_decisions (\n\trecord_id UUID NOT NULL, \n\tversion INTEGER NOT NULL, \n\tstage INTEGER NOT NULL, \n\tdecision VARCHAR NOT NULL, \n\tcomments VARCHAR NOT NULL, \n\tprior_status VARCHAR NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(tenant_id, record_id) REFERENCES audit_records (tenant_id, id), \n\tUNIQUE (record_id, version, stage, decision), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_audit_review_decisions_tenant_id ON audit_review_decisions (tenant_id)"
    )
    op.execute("ALTER TABLE audit_review_decisions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_review_decisions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_review_decisions USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON audit_record_versions FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON audit_review_decisions FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON audit_evidence_versions FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    connection = op.get_bind()
    defaults = {
        "Platform Administrator": ["platform.manage"],
        "Firm Administrator": [
            "accounting.import",
            "accounting.map",
            "accounting.read",
            "ai.audit.execute",
            "ai.execute",
            "ai.read",
            "analytics.read",
            "analytics.run",
            "audit.evidence.review",
            "audit.evidence.upload",
            "audit.export",
            "audit.finding.create",
            "audit.finding.resolve",
            "audit.materiality.approve",
            "audit.materiality.prepare",
            "audit.plan",
            "audit.program.prepare",
            "audit.program.review",
            "audit.read",
            "audit.risk.approve",
            "audit.risk.prepare",
            "audit.testing.execute",
            "clients.read",
            "clients.write",
            "connectors.manage",
            "engagement.accept",
            "engagement.accept.prepare",
            "engagement.archive",
            "engagement.assign",
            "engagement.create",
            "engagement.finalize",
            "engagement.quality_review",
            "engagements.read",
            "engagements.write",
            "entities.read",
            "entities.write",
            "financial_ai.approve",
            "financial_ai.execute",
            "independence.declare",
            "independence.review",
            "jobs.execute",
            "jobs.read",
            "members.manage",
            "methodology.manage",
            "sampling.run",
            "tenant.manage",
            "users.assign_roles",
            "users.invite",
            "workingpaper.approve",
            "workingpaper.create",
            "workingpaper.review",
        ],
        "Audit Partner": [
            "ai.audit.execute",
            "ai.execute",
            "ai.read",
            "audit.evidence.review",
            "audit.evidence.upload",
            "audit.export",
            "audit.finding.create",
            "audit.finding.resolve",
            "audit.materiality.approve",
            "audit.materiality.prepare",
            "audit.plan",
            "audit.program.prepare",
            "audit.program.review",
            "audit.read",
            "audit.risk.approve",
            "audit.risk.prepare",
            "audit.testing.execute",
            "clients.read",
            "engagement.accept",
            "engagement.accept.prepare",
            "engagement.archive",
            "engagement.assign",
            "engagement.finalize",
            "engagements.read",
            "engagements.write",
            "entities.read",
            "independence.declare",
            "independence.review",
            "jobs.read",
            "workingpaper.approve",
            "workingpaper.create",
            "workingpaper.review",
        ],
        "Audit Manager": [
            "ai.audit.execute",
            "ai.execute",
            "ai.read",
            "audit.evidence.review",
            "audit.evidence.upload",
            "audit.finding.create",
            "audit.finding.resolve",
            "audit.materiality.prepare",
            "audit.plan",
            "audit.program.prepare",
            "audit.program.review",
            "audit.read",
            "audit.risk.prepare",
            "audit.testing.execute",
            "clients.read",
            "engagement.accept.prepare",
            "engagement.assign",
            "engagements.read",
            "engagements.write",
            "entities.read",
            "independence.declare",
            "workingpaper.approve",
            "workingpaper.create",
            "workingpaper.review",
        ],
        "Senior Auditor": [
            "ai.audit.execute",
            "ai.execute",
            "ai.read",
            "audit.evidence.upload",
            "audit.finding.create",
            "audit.materiality.prepare",
            "audit.plan",
            "audit.program.prepare",
            "audit.read",
            "audit.risk.prepare",
            "audit.testing.execute",
            "clients.read",
            "engagement.accept.prepare",
            "engagements.read",
            "entities.read",
            "independence.declare",
            "workingpaper.create",
        ],
        "Auditor": [
            "ai.audit.execute",
            "audit.evidence.upload",
            "audit.finding.create",
            "audit.materiality.prepare",
            "audit.plan",
            "audit.program.prepare",
            "audit.read",
            "audit.risk.prepare",
            "audit.testing.execute",
            "clients.read",
            "engagement.accept.prepare",
            "engagements.read",
            "entities.read",
            "independence.declare",
            "workingpaper.create",
        ],
        "Tax Manager": [
            "clients.read",
            "entities.read",
            "engagements.read",
            "engagements.write",
            "ai.read",
            "ai.execute",
        ],
        "Tax Consultant": ["clients.read", "entities.read", "engagements.read"],
        "Client Viewer": ["portal.read"],
        "Managing Partner": [
            "ai.audit.execute",
            "ai.execute",
            "ai.read",
            "audit.evidence.review",
            "audit.evidence.upload",
            "audit.export",
            "audit.finding.create",
            "audit.finding.resolve",
            "audit.materiality.approve",
            "audit.materiality.prepare",
            "audit.plan",
            "audit.program.prepare",
            "audit.program.review",
            "audit.read",
            "audit.risk.approve",
            "audit.risk.prepare",
            "audit.testing.execute",
            "clients.read",
            "engagement.accept",
            "engagement.accept.prepare",
            "engagement.archive",
            "engagement.assign",
            "engagement.finalize",
            "engagements.read",
            "engagements.write",
            "entities.read",
            "independence.declare",
            "independence.review",
            "jobs.read",
            "workingpaper.approve",
            "workingpaper.create",
            "workingpaper.review",
        ],
        "Audit Partner / Chartered Accountant": [
            "ai.audit.execute",
            "ai.execute",
            "ai.read",
            "audit.evidence.review",
            "audit.evidence.upload",
            "audit.export",
            "audit.finding.create",
            "audit.finding.resolve",
            "audit.materiality.approve",
            "audit.materiality.prepare",
            "audit.plan",
            "audit.program.prepare",
            "audit.program.review",
            "audit.read",
            "audit.risk.approve",
            "audit.risk.prepare",
            "audit.testing.execute",
            "clients.read",
            "engagement.accept",
            "engagement.accept.prepare",
            "engagement.archive",
            "engagement.assign",
            "engagement.finalize",
            "engagements.read",
            "engagements.write",
            "entities.read",
            "independence.declare",
            "independence.review",
            "jobs.read",
            "workingpaper.approve",
            "workingpaper.create",
            "workingpaper.review",
        ],
        "Audit Trainee": [
            "audit.read",
            "workingpaper.create",
            "audit.testing.execute",
            "audit.evidence.upload",
            "independence.declare",
            "engagements.read",
        ],
        "Quality Reviewer": [
            "audit.read",
            "engagements.read",
            "engagement.quality_review",
            "independence.declare",
            "workingpaper.review",
        ],
        "Read-only Reviewer": ["audit.read", "engagements.read"],
        "Firm Operations User": ["users.invite", "audit.read", "engagements.read"],
        "Platform Super Admin": ["platform.manage"],
        "Platform Support Administrator": ["platform.support"],
        "Client Administrator": ["portal.read", "portal.respond"],
        "Client Finance Manager": ["portal.read", "portal.respond"],
        "Client Accountant": ["portal.read", "portal.respond"],
        "Client Document Contributor": ["portal.read", "portal.respond"],
    }
    for name, codes in defaults.items():
        rid = connection.scalar(sa.text("SELECT id FROM roles WHERE name=:name"), {"name": name})
        if rid is None:
            rid = uuid.uuid4()
            connection.execute(
                sa.text("INSERT INTO roles (id,name) VALUES (:id,:name)"), {"id": rid, "name": name}
            )
        for code in codes:
            pid = connection.scalar(
                sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}
            )
            if pid is None:
                pid = uuid.uuid4()
                connection.execute(
                    sa.text("INSERT INTO permissions (id,code) VALUES (:id,:code)"),
                    {"id": pid, "code": code},
                )
            connection.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id,permission_id) VALUES (:rid,:pid) ON CONFLICT DO NOTHING"
                ),
                {"rid": rid, "pid": pid},
            )


def downgrade():
    raise RuntimeError(
        "Phase 4 contains immutable professional records; restore a verified backup for rollback"
    )
