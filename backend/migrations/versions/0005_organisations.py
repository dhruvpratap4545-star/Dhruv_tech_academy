"""The organisation level: a group of institutes under one owner.

Revision ID: 0005_organisations
Revises: 0004_override_indexes

Adds a level *above* institute — "JSPM Group of Institutes", "MIT" — so one administrator
can run four colleges without being handed the whole platform.

**Nothing existing changes meaning.** `institutes.organisation_id` is nullable and starts
null for every row, so every scope in the database stays exactly what it was: an institute
with no organisation behaves identically to one from before this level existed. There is no
backfill, because there is nothing to back-fill into.

The two new `one_level` check constraints are the part worth reading. An assignment or a
grant sits at exactly one level; naming both an organisation and an institute would be two
different grants written in one row, and every containment test would then disagree about
which one it is.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005_organisations"
down_revision: str | None = "0004_override_indexes"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "organisations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("logo_url", sa.String(length=512), nullable=True),
        sa.Column("contact_email", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organisations")),
        sa.UniqueConstraint("code", name="uq_organisations_code"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="organisations_status"),
    )

    # RESTRICT, not CASCADE: deleting an organisation must never silently take four
    # colleges and everybody inside them with it.
    op.add_column("institutes", sa.Column("organisation_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_institutes_organisation_id_organisations"),
        "institutes",
        "organisations",
        ["organisation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_institutes_organisation_id", "institutes", ["organisation_id"])

    for table in ("user_role_assignments", "user_permission_grants"):
        op.add_column(table, sa.Column("organisation_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_{table}_organisation_id_organisations"),
            table,
            "organisations",
            ["organisation_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(f"ix_{table}_organisation_id", table, ["organisation_id"])
        op.create_check_constraint(
            f"{table}_one_level",
            table,
            "organisation_id IS NULL OR institute_id IS NULL",
        )

    # Roles may now be defined at the new level. The old constraint listed three values
    # and has to be replaced rather than extended.
    op.drop_constraint(op.f("ck_roles_roles_scope_level"), "roles", type_="check")
    op.create_check_constraint(
        "roles_scope_level",
        "roles",
        "scope_level IN ('platform', 'organisation', 'institute', 'branch')",
    )


def downgrade() -> None:
    # Narrow the roles constraint back first: any organisation-level role has to be gone
    # before the column it depends on is dropped, and failing here is better than leaving
    # a half-reverted schema.
    op.drop_constraint(op.f("ck_roles_roles_scope_level"), "roles", type_="check")
    op.create_check_constraint(
        "roles_scope_level",
        "roles",
        "scope_level IN ('platform', 'institute', 'branch')",
    )

    for table in ("user_permission_grants", "user_role_assignments"):
        op.drop_constraint(op.f(f"ck_{table}_{table}_one_level"), table, type_="check")
        op.drop_index(f"ix_{table}_organisation_id", table_name=table)
        op.drop_constraint(
            op.f(f"fk_{table}_organisation_id_organisations"), table, type_="foreignkey"
        )
        op.drop_column(table, "organisation_id")

    op.drop_index("ix_institutes_organisation_id", table_name="institutes")
    op.drop_constraint(
        op.f("fk_institutes_organisation_id_organisations"), "institutes", type_="foreignkey"
    )
    op.drop_column("institutes", "organisation_id")

    op.drop_table("organisations")
