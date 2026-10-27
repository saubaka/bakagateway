"""Personal center, avatar reference, device metadata and email change."""

import sqlalchemy as sa
from alembic import op

revision = "0003_personal_center"
down_revision = "0002_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("avatar_key", sa.String(40)))
    op.add_column(
        "auth_sessions",
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.add_column(
        "auth_sessions",
        sa.Column("device_label", sa.String(80), nullable=False, server_default="未知设备"),
    )
    op.add_column(
        "auth_sessions", sa.Column("ip_address", sa.String(64), nullable=False, server_default="")
    )
    op.execute("UPDATE auth_sessions SET last_seen_at = created_at")
    for name in ["last_seen_at", "device_label", "ip_address"]:
        op.alter_column("auth_sessions", name, server_default=None)
    op.drop_constraint("ck_challenge_purpose", "email_challenges", type_="check")
    op.create_check_constraint(
        "ck_challenge_purpose", "email_challenges", "purpose IN ('register','reset','email-change')"
    )


def downgrade():
    op.execute("DELETE FROM email_challenges WHERE purpose = 'email-change'")
    op.drop_constraint("ck_challenge_purpose", "email_challenges", type_="check")
    op.create_check_constraint(
        "ck_challenge_purpose", "email_challenges", "purpose IN ('register','reset')"
    )
    for name in ["ip_address", "device_label", "last_seen_at"]:
        op.drop_column("auth_sessions", name)
    op.drop_column("users", "avatar_key")
