"""Explicit period locks; existing periods remain open for compatibility."""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE financial_periods ADD COLUMN lock_state TEXT NOT NULL DEFAULT 'OPEN'")
    op.execute("ALTER TABLE financial_periods ADD COLUMN lock_version INTEGER NOT NULL DEFAULT 1")
    op.execute(
        "ALTER TABLE financial_periods ADD CONSTRAINT valid_period_lock CHECK (lock_state IN ('OPEN','LOCKED') AND lock_version > 0)"
    )


def downgrade():
    raise RuntimeError("Preserve period control history; use a reviewed forward migration")
