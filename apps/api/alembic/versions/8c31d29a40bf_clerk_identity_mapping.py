"""Add Clerk subject mapping without changing local owner IDs."""

from alembic import op
import sqlalchemy as sa

revision = "8c31d29a40bf"
down_revision = "af78127a72ed"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("clerk_user_id", sa.String(), nullable=True))
        batch.create_unique_constraint("uq_users_clerk_user_id", ["clerk_user_id"])


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_clerk_user_id", type_="unique")
        batch.drop_column("clerk_user_id")
