"""Support stable tenant ledger pagination without sorting the full population."""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_lines_tenant_created_id", "journal_lines", ["tenant_id", "created_at", "id"]
    )


def downgrade():
    op.drop_index("ix_lines_tenant_created_id", table_name="journal_lines")
