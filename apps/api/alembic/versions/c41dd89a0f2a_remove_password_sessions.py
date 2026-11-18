"""Remove local password and server-session auth storage."""

import sqlalchemy as sa

from alembic import op

revision = "c41dd89a0f2a"
down_revision = "d7a0128c9be1"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("sessions")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("password_hash")


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("password_hash", sa.String(), nullable=True))
    op.create_table(
        "sessions",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
