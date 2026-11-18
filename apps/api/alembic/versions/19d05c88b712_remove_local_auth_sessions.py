"""Remove obsolete local sessions only; retain owner IDs and migration digests."""

from alembic import op
import sqlalchemy as sa

revision = "19d05c88b712"
down_revision = "8c31d29a40bf"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("sessions")


def downgrade():
    # Restoring the schema does not resurrect any old authenticated session.
    op.create_table(
        "sessions",
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
