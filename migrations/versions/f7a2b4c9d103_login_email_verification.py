"""Add login email verification for unrecognized devices and networks.

Revision ID: f7a2b4c9d103
Create Date: 2026-08-19
"""

import sqlalchemy as sa
from alembic import op

revision = "f7a2b4c9d103"
down_revision = "e8f4a6b1c925"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "login_logs",
        sa.Column("client_ip_digest", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_login_logs_client_ip_digest",
        "login_logs",
        ["client_ip_digest"],
    )
    with op.batch_alter_table("email_challenges") as batch_op:
        batch_op.drop_constraint("ck_email_challenge_purpose", type_="check")
        batch_op.create_check_constraint(
            "ck_email_challenge_purpose",
            "purpose IN ('register', 'verify_email', 'change_email', 'password_reset', "
            "'login_verification')",
        )
    with op.batch_alter_table("mail_templates") as batch_op:
        batch_op.drop_constraint("ck_mail_template_key", type_="check")
        batch_op.create_check_constraint(
            "ck_mail_template_key",
            "key IN ("
            "'smtp_test', "
            "'admin_email_verification', "
            "'registration', "
            "'account_email_verification', "
            "'change_email', "
            "'password_reset', "
            "'login_verification'"
            ")",
        )


def downgrade() -> None:
    with op.batch_alter_table("mail_templates") as batch_op:
        batch_op.drop_constraint("ck_mail_template_key", type_="check")
        batch_op.create_check_constraint(
            "ck_mail_template_key",
            "key IN ("
            "'smtp_test', "
            "'admin_email_verification', "
            "'registration', "
            "'account_email_verification', "
            "'change_email', "
            "'password_reset'"
            ")",
        )
    with op.batch_alter_table("email_challenges") as batch_op:
        batch_op.drop_constraint("ck_email_challenge_purpose", type_="check")
        batch_op.create_check_constraint(
            "ck_email_challenge_purpose",
            "purpose IN ('register', 'verify_email', 'change_email', 'password_reset')",
        )
    op.drop_index("ix_login_logs_client_ip_digest", table_name="login_logs")
    op.drop_column("login_logs", "client_ip_digest")
