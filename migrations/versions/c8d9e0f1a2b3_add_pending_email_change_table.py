"""Add pending email change table for verified email replacement.

Revision ID: c8d9e0f1a2b3
Create Date: 2026-08-14
"""

import sqlalchemy as sa
from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "b7e3d5f9a614"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_email_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("new_email_digest", sa.String(length=64), nullable=False),
        sa.Column("new_email_ciphertext", sa.Text(), nullable=False),
        sa.Column("old_email_digest", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.Index("ix_pending_email_changes_user_id", "user_id"),
        sa.Index("ix_pending_email_changes_new_email_digest", "new_email_digest"),
        sa.Index("ix_pending_email_changes_expires_at", "expires_at"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pending_email_changes_expires_at",
        table_name="pending_email_changes",
    )
    op.drop_index(
        "ix_pending_email_changes_new_email_digest",
        table_name="pending_email_changes",
    )
    op.drop_index("ix_pending_email_changes_user_id", table_name="pending_email_changes")
    op.drop_table("pending_email_changes")
