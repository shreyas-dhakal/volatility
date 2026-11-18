"""Persist generated Graphify JSON for download."""

import sqlalchemy as sa
from alembic import op

revision = "bfa4d2219e05"
down_revision = "c41dd89a0f2a"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "technical_graphs", sa.Column("export_json", sa.JSON(), nullable=True)
    )


def downgrade():
    op.drop_column("technical_graphs", "export_json")
