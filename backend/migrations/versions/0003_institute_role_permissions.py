"""Per-institute adjustments to what a role allows.

Revision ID: 0003_institute_role_permissions
Revises: 0002_access_control

One new table, nothing altered. An institute with no customisation has no rows, so this
changes nobody's access on the day it ships — the engine reads the difference and finds
none.

The table records the *difference* from the role's definition, not a copy of it. That
matters for upgrades: a copy would freeze on the day it was taken, so adding a permission
to Faculty in a later release would silently skip every institute that had ever customised
the role.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_institute_role_permissions"
down_revision: str | None = "0002_access_control"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "institute_role_permissions",
        sa.Column("institute_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effect", sa.String(length=8), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
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
        # The triple is the row: one institute's verdict on one permission of one role.
        sa.PrimaryKeyConstraint(
            "institute_id", "role_id", "permission_id", name="pk_institute_role_permissions"
        ),
        sa.ForeignKeyConstraint(
            ["institute_id"],
            ["institutes.id"],
            name="fk_irp_institute_id_institutes",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name="fk_irp_role_id_roles", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_irp_permission_id_permissions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_irp_created_by_users", ondelete="SET NULL"
        ),
        sa.CheckConstraint("effect IN ('allow', 'deny')", name="institute_role_permissions_effect"),
    )
    # The permission check loads overrides for one person's institutes and roles; the
    # primary key already leads with institute_id, so this covers the other direction —
    # "which institutes have customised this role?", asked by the roles screen.
    op.create_index("ix_institute_role_permissions_role", "institute_role_permissions", ["role_id"])


def downgrade() -> None:
    op.drop_index("ix_institute_role_permissions_role", table_name="institute_role_permissions")
    op.drop_table("institute_role_permissions")
