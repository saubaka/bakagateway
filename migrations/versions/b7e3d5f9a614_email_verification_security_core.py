"""Add the encrypted email-verification security core."""

import sqlalchemy as sa
from alembic import op

revision = "b7e3d5f9a614"
down_revision = "e6f1b9c4d802"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mail_providers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("security_mode", sa.String(length=20), nullable=False),
        sa.Column("username", sa.String(length=254), nullable=False),
        sa.Column("password_ciphertext", sa.Text(), nullable=False),
        sa.Column("sender_email", sa.String(length=254), nullable=False),
        sa.Column("sender_name", sa.String(length=100), nullable=False),
        sa.Column("reply_to", sa.String(length=254), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_succeeded", sa.Boolean(), nullable=True),
        sa.Column("last_test_error", sa.String(length=240), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("port BETWEEN 1 AND 65535", name="ck_mail_provider_port"),
        sa.CheckConstraint(
            "security_mode IN ('ssl', 'starttls', 'plain')",
            name="ck_mail_provider_security_mode",
        ),
        sa.CheckConstraint(
            "timeout_seconds BETWEEN 3 AND 60",
            name="ck_mail_provider_timeout",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mail_providers_is_active", "mail_providers", ["is_active"])
    op.create_index("ix_mail_providers_is_default", "mail_providers", ["is_default"])
    op.create_index("ix_mail_providers_name", "mail_providers", ["name"], unique=True)

    op.create_table(
        "pending_registrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("email_digest", sa.String(length=64), nullable=False),
        sa.Column("email_ciphertext", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("continuation_ciphertext", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pending_registrations_email_digest",
        "pending_registrations",
        ["email_digest"],
    )
    op.create_index(
        "ix_pending_registrations_expires_at",
        "pending_registrations",
        ["expires_at"],
    )
    op.create_index(
        "ix_pending_registrations_public_id",
        "pending_registrations",
        ["public_id"],
        unique=True,
    )
    op.create_index(
        "ix_pending_registrations_username",
        "pending_registrations",
        ["username"],
    )

    op.create_table(
        "email_challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("pending_registration_id", sa.Integer(), nullable=True),
        sa.Column("recipient_digest", sa.String(length=64), nullable=False),
        sa.Column("recipient_ciphertext", sa.Text(), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_email_challenge_attempt_count",
        ),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 20",
            name="ck_email_challenge_max_attempts",
        ),
        sa.CheckConstraint(
            "purpose IN ('register', 'verify_email', 'change_email', 'password_reset')",
            name="ck_email_challenge_purpose",
        ),
        sa.ForeignKeyConstraint(
            ["pending_registration_id"],
            ["pending_registrations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_challenges_created_at", "email_challenges", ["created_at"])
    op.create_index("ix_email_challenges_expires_at", "email_challenges", ["expires_at"])
    op.create_index(
        "ix_email_challenges_pending_registration_id",
        "email_challenges",
        ["pending_registration_id"],
    )
    op.create_index("ix_email_challenges_public_id", "email_challenges", ["public_id"], unique=True)
    op.create_index("ix_email_challenges_purpose", "email_challenges", ["purpose"])
    op.create_index(
        "ix_email_challenges_recipient_digest",
        "email_challenges",
        ["recipient_digest"],
    )
    op.create_index(
        "ix_email_challenges_request_fingerprint",
        "email_challenges",
        ["request_fingerprint"],
    )
    op.create_index("ix_email_challenges_user_id", "email_challenges", ["user_id"])
    op.create_index(
        "ix_email_challenge_recipient_purpose_created",
        "email_challenges",
        ["recipient_digest", "purpose", "created_at"],
    )
    op.create_index(
        "ix_email_challenge_fingerprint_created",
        "email_challenges",
        ["request_fingerprint", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_email_challenge_fingerprint_created", table_name="email_challenges")
    op.drop_index("ix_email_challenge_recipient_purpose_created", table_name="email_challenges")
    op.drop_index("ix_email_challenges_user_id", table_name="email_challenges")
    op.drop_index("ix_email_challenges_request_fingerprint", table_name="email_challenges")
    op.drop_index("ix_email_challenges_recipient_digest", table_name="email_challenges")
    op.drop_index("ix_email_challenges_purpose", table_name="email_challenges")
    op.drop_index("ix_email_challenges_public_id", table_name="email_challenges")
    op.drop_index("ix_email_challenges_pending_registration_id", table_name="email_challenges")
    op.drop_index("ix_email_challenges_expires_at", table_name="email_challenges")
    op.drop_index("ix_email_challenges_created_at", table_name="email_challenges")
    op.drop_table("email_challenges")

    op.drop_index("ix_pending_registrations_username", table_name="pending_registrations")
    op.drop_index("ix_pending_registrations_public_id", table_name="pending_registrations")
    op.drop_index("ix_pending_registrations_expires_at", table_name="pending_registrations")
    op.drop_index("ix_pending_registrations_email_digest", table_name="pending_registrations")
    op.drop_table("pending_registrations")

    op.drop_index("ix_mail_providers_name", table_name="mail_providers")
    op.drop_index("ix_mail_providers_is_default", table_name="mail_providers")
    op.drop_index("ix_mail_providers_is_active", table_name="mail_providers")
    op.drop_table("mail_providers")
