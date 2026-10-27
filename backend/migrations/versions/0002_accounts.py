"""Account, server-side session and email challenge storage."""

import sqlalchemy as sa
from alembic import op

revision = "0002_accounts"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(32), nullable=False, unique=True),
        sa.Column("nickname", sa.String(40), nullable=False),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("email_verified", sa.Boolean, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("auth_version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user','admin')", name="ck_user_role"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("user_version", sa.Integer),
        sa.Column("flow_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    for name in ["user_id", "expires_at", "revoked_at"]:
        op.create_index("ix_auth_sessions_" + name, "auth_sessions", [name])
    op.create_table(
        "email_challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("user_version", sa.Integer),
        sa.Column("encrypted_data", sa.Text, nullable=False),
        sa.Column("code_digest", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("send_count", sa.Integer, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resend_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("purpose IN ('register','reset')", name="ck_challenge_purpose"),
    )
    for name in ["session_id", "expires_at"]:
        op.create_index("ix_email_challenges_" + name, "email_challenges", [name])
    op.create_table(
        "mail_configuration",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("encrypted_data", sa.Text, nullable=False),
    )
    settings = op.create_table(
        "auth_settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("registration_open", sa.Boolean, nullable=False),
    )
    op.bulk_insert(settings, [{"id": 1, "registration_open": False}])
    op.create_table(
        "auth_rates",
        sa.Column("bucket", sa.String(64), primary_key=True),
        sa.Column("count", sa.Integer, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_rates_expires_at", "auth_rates", ["expires_at"])


def downgrade():
    for table in [
        "auth_rates",
        "auth_settings",
        "mail_configuration",
        "email_challenges",
        "auth_sessions",
        "users",
    ]:
        op.drop_table(table)
