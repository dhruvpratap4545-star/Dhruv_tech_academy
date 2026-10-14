"""Guardians: which adult is responsible for which learner.

Revision ID: 0006_guardians
Revises: 0005_organisations

Many-to-many in both directions, because a parent commonly has two children at the same
school and a child commonly has two parents. Modelling either side as "one" produces a
product that cannot describe an ordinary family.

The row is also the consent record. Under the DPDP Act a child's personal data is processed
on the basis of verifiable parental consent; ``verified_at`` stays null until the adult has
completed setup at their own address, which is what makes that consent verifiable rather
than asserted by whoever typed the row in.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006_guardians"
down_revision: str | None = "0005_organisations"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "guardians",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("parent_user_id", sa.Uuid(), nullable=False),
        sa.Column("student_user_id", sa.Uuid(), nullable=False),
        sa.Column("relationship", sa.String(length=40), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("linked_by", sa.Uuid(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guardians")),
        sa.ForeignKeyConstraint(
            ["parent_user_id"],
            ["users.id"],
            name=op.f("fk_guardians_parent_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_user_id"],
            ["users.id"],
            name=op.f("fk_guardians_student_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["linked_by"],
            ["users.id"],
            name=op.f("fk_guardians_linked_by_users"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "parent_user_id", "student_user_id", name="uq_guardians_parent_student"
        ),
        # A person cannot be their own guardian. It closes a loop that would otherwise let
        # a student read themselves as a parent and inherit a second set of permissions.
        sa.CheckConstraint("parent_user_id <> student_user_id", name="guardians_not_self"),
    )
    op.create_index("ix_guardians_student_user_id", "guardians", ["student_user_id"])
    op.create_index("ix_guardians_parent_user_id", "guardians", ["parent_user_id"])


def downgrade() -> None:
    op.drop_index("ix_guardians_parent_user_id", table_name="guardians")
    op.drop_index("ix_guardians_student_user_id", table_name="guardians")
    op.drop_table("guardians")
