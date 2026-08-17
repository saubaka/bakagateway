"""Add customizable email templates for administrator-managed mail content.

Revision ID: e8f4a6b1c925
Create Date: 2026-08-15
"""

import sqlalchemy as sa
from alembic import op

revision = "e8f4a6b1c925"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mail_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("subject", sa.String(length=150), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "key IN ("
            "'smtp_test', "
            "'admin_email_verification', "
            "'registration', "
            "'account_email_verification', "
            "'change_email', "
            "'password_reset'"
            ")",
            name="ck_mail_template_key",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mail_templates_key", "mail_templates", ["key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_mail_templates_key", table_name="mail_templates")
    op.drop_table("mail_templates")
