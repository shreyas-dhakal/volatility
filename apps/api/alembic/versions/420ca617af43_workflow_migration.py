"""Persist workflow migration drafts, durable jobs, and approvals."""

import sqlalchemy as sa

from alembic import op

revision = "420ca617af43"
down_revision = "bfa4d2219e05"
branch_labels = None
depends_on = None


def identity():
    return (
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )


def foreign(name, table, *, unique=False):
    return sa.Column(
        name,
        sa.String(),
        sa.ForeignKey(table + ".id", ondelete="CASCADE"),
        nullable=False,
        unique=unique,
    )


def upgrade():
    op.create_table(
        "workflow_migration",
        *identity(),
        foreign("revision_id", "design_revision"),
        sa.Column("operation_id", sa.String(), nullable=False),
        sa.Column("selection_json", sa.JSON(), nullable=False),
        sa.Column("scenarios_json", sa.JSON(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("revision_id", "operation_id"),
    )
    op.create_table(
        "workflow_migration_job",
        *identity(),
        foreign("migration_id", "workflow_migration"),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON()),
        sa.Column("error", sa.Text()),
        sa.Column("claim_token", sa.String()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("migration_id", "request_id"),
    )
    op.create_table(
        "workflow_baseline",
        *identity(),
        foreign("migration_id", "workflow_migration", unique=True),
        foreign("capture_id", "workflow_migration_job"),
        sa.Column("approved_by", sa.String(), nullable=False),
        sa.Column("artifact_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "workflow_accepted_patch",
        *identity(),
        foreign("migration_id", "workflow_migration"),
        foreign("job_id", "workflow_migration_job", unique=True),
        sa.Column("approved_by", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
    )
    for table in (
        "workflow_migration",
        "workflow_migration_job",
        "workflow_baseline",
        "workflow_accepted_patch",
    ):
        op.create_index("ix_" + table + "_project_id", table, ["project_id"])
    for table, column in (
        ("workflow_migration_job", "migration_id"),
        ("workflow_migration_job", "status"),
        ("workflow_accepted_patch", "migration_id"),
    ):
        op.create_index("ix_" + table + "_" + column, table, [column])


def downgrade():
    for table in (
        "workflow_accepted_patch",
        "workflow_baseline",
        "workflow_migration_job",
        "workflow_migration",
    ):
        op.drop_table(table)
