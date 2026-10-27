"""Administrator settings, audit and application icons; preserve existing identities."""

import sqlalchemy as sa
from alembic import op

revision = "0005_admin"
down_revision = "0004_oauth"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mail_configuration", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.alter_column("mail_configuration", "version", server_default=None)
    op.add_column("oauth_clients", sa.Column("icon_key", sa.String(40), nullable=True))
    site = op.create_table(
        "site_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_name", sa.String(60), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("support_email", sa.String(254), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.bulk_insert(
        site,
        [
            {
                "id": 1,
                "site_name": "baka 身份平台",
                "description": "一个账号，连接你的应用。",
                "support_email": "",
                "version": 1,
            }
        ],
    )
    op.create_table(
        "admin_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_name", sa.String(32), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("target_id", sa.String(48), nullable=False),
        sa.Column("summary", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_audit_action", "admin_audit", ["action"])
    op.create_index("ix_admin_audit_created_at", "admin_audit", ["created_at"])


def downgrade():
    op.drop_table("admin_audit")
    op.drop_table("site_settings")
    op.drop_column("oauth_clients", "icon_key")
    op.drop_column("mail_configuration", "version")
