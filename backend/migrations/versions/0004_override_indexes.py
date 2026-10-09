"""Indexes behind the foreign keys of the per-institute override table.

PostgreSQL indexes the referencing side of a foreign key only when you ask it to. Without
an index, every `DELETE FROM permissions` and every `DELETE FROM users` has to sequentially
scan `institute_role_permissions` to prove the RESTRICT/SET NULL clause is satisfied —
which is fine while the table is small and quietly stops being fine later, in a transaction
nobody is watching.

`role_id` already has one, from 0003. These are the two it missed.

Revision ID: 0004_override_indexes
Revises: 0003_institute_role_permissions
"""

from __future__ import annotations

from alembic import op

revision: str = "0004_override_indexes"
down_revision: str | None = "0003_institute_role_permissions"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_index(
        "ix_institute_role_permissions_permission",
        "institute_role_permissions",
        ["permission_id"],
    )
    op.create_index(
        "ix_institute_role_permissions_created_by",
        "institute_role_permissions",
        ["created_by"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_institute_role_permissions_created_by", table_name="institute_role_permissions"
    )
    op.drop_index(
        "ix_institute_role_permissions_permission", table_name="institute_role_permissions"
    )
