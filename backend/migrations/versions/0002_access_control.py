"""Custom roles and per-user permission grants.

Revision ID: 0002_access_control
Revises: 0001_baseline

Two independent changes, both additive, all safe to run against a live database:

* ``roles`` gains the columns a custom role needs. Every existing row is a built-in, so
  ``is_system`` is already true and ``institute_id`` stays NULL — the check constraint
  holds for the existing data without a backfill.
* ``user_permission_grants`` is new.
The daily sign-in chart needed no new index: the baseline's
``ix_audit_logs_action_created_at`` is already the right shape for it.

Nothing is dropped and nothing is rewritten, so this needs no expand/contract dance and no
downtime window.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_access_control"
down_revision: str | None = "0001_baseline"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ custom roles
    op.add_column("roles", sa.Column("description", sa.String(length=255), nullable=True))
    op.add_column(
        "roles",
        sa.Column("institute_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "roles",
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_roles_institute_id_institutes",
        "roles",
        "institutes",
        ["institute_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_roles_created_by_users",
        "roles",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_roles_institute_id", "roles", ["institute_id"])
    op.create_check_constraint("roles_rank_positive", "roles", "rank > 0")
    op.create_check_constraint(
        "roles_custom_needs_institute",
        "roles",
        "(is_system AND institute_id IS NULL) OR (NOT is_system AND institute_id IS NOT NULL)",
    )

    # -------------------------------------------------------- per-user permission grants
    op.create_table(
        "user_permission_grants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effect", sa.String(length=8), nullable=False, server_default="allow"),
        sa.Column("institute_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_permission_grants"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_upg_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_upg_permission_id_permissions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["institute_id"],
            ["institutes.id"],
            name="fk_upg_institute_id_institutes",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branches.id"], name="fk_upg_branch_id_branches", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"], ["users.id"], name="fk_upg_granted_by_users", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"], ["users.id"], name="fk_upg_revoked_by_users", ondelete="SET NULL"
        ),
        sa.CheckConstraint("effect IN ('allow', 'deny')", name="user_permission_grants_effect"),
        sa.CheckConstraint(
            "branch_id IS NULL OR institute_id IS NOT NULL",
            name="user_permission_grants_branch_needs_institute",
        ),
    )
    # Partial, matching the permission check: it only ever reads live rows, and revoked
    # ones are history it must not pay to skip over.
    op.create_index(
        "ix_user_permission_grants_user_id_live",
        "user_permission_grants",
        ["user_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_user_permission_grants_institute_id", "user_permission_grants", ["institute_id"]
    )

    # No index is added for the daily sign-in chart: ``ix_audit_logs_action_created_at``
    # from the baseline is already (action, created_at), which is exactly the shape that
    # query needs — equality on action, range on created_at.


def downgrade() -> None:
    op.drop_index("ix_user_permission_grants_institute_id", table_name="user_permission_grants")
    op.drop_index("ix_user_permission_grants_user_id_live", table_name="user_permission_grants")
    op.drop_table("user_permission_grants")
    op.drop_constraint("roles_custom_needs_institute", "roles", type_="check")
    op.drop_constraint("roles_rank_positive", "roles", type_="check")
    op.drop_index("ix_roles_institute_id", table_name="roles")
    op.drop_constraint("fk_roles_created_by_users", "roles", type_="foreignkey")
    op.drop_constraint("fk_roles_institute_id_institutes", "roles", type_="foreignkey")
    op.drop_column("roles", "created_by")
    op.drop_column("roles", "institute_id")
    op.drop_column("roles", "description")
