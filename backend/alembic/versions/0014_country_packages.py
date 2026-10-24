"""User country context and immutable engagement package receipts; no financial rewrites."""

import hashlib
import json
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    common = "tenant_id UUID NOT NULL REFERENCES tenants(id), created_by UUID REFERENCES users(id), id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    op.execute(
        f"CREATE TABLE country_preferences ({common}, user_id UUID NOT NULL REFERENCES users(id), country VARCHAR NOT NULL, version INTEGER NOT NULL, UNIQUE(tenant_id,user_id))"
    )
    op.execute(
        f"CREATE TABLE engagement_jurisdictions ({common}, engagement_id UUID NOT NULL, country VARCHAR NOT NULL, package_version VARCHAR NOT NULL, package_sha256 VARCHAR NOT NULL, manifest JSONB NOT NULL, UNIQUE(tenant_id,engagement_id), FOREIGN KEY(tenant_id,engagement_id) REFERENCES engagements(tenant_id,id))"
    )
    for name in ["country_preferences", "engagement_jurisdictions"]:
        op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])
        op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {name} USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)"
        )
    frozen = json.loads(
        (Path(__file__).resolve().parents[1] / "data/0014-country-packages.json").read_text(
            encoding="utf8"
        )
    )
    connection = op.get_bind()
    for tenant in connection.execute(sa.text("SELECT id FROM tenants")).scalars().all():
        connection.execute(
            sa.text("SELECT set_config('app.tenant_id',:tenant,true)"), {"tenant": str(tenant)}
        )
        rows = (
            connection.execute(
                sa.text(
                    "SELECT e.id, e.created_by, l.country FROM engagements e JOIN legal_entities l ON e.entity_id=l.id AND e.tenant_id=l.tenant_id WHERE e.tenant_id=:tenant"
                ),
                {"tenant": tenant},
            )
            .mappings()
            .all()
        )
        for row in rows:
            manifest = frozen[row["country"]]
            payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
            connection.execute(
                sa.text(
                    "INSERT INTO engagement_jurisdictions (id,tenant_id,created_by,engagement_id,country,package_version,package_sha256,manifest) VALUES (:id,:tenant,:actor,:eid,:country,:version,:sha,cast(:manifest as jsonb))"
                ),
                {
                    "id": uuid.uuid4(),
                    "tenant": tenant,
                    "actor": row["created_by"],
                    "eid": row["id"],
                    "country": row["country"],
                    "version": manifest["version"],
                    "sha": hashlib.sha256(payload.encode()).hexdigest(),
                    "manifest": payload,
                },
            )
    connection.execute(sa.text("SELECT set_config('app.tenant_id','',true)"))
    op.execute(
        "CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON engagement_jurisdictions FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )


def downgrade():
    raise RuntimeError("Country package history must be retained; use a reviewed forward repair")
