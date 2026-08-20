from __future__ import annotations

import json
from datetime import UTC, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def utcnow() -> datetime:
    return datetime.now(UTC)


user_roles = db.Table(
    "user_roles",
    db.Column(
        "user_id", db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    ),
    db.Column(
        "role_id", db.Integer, db.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    ),
)

role_permissions = db.Table(
    "role_permissions",
    db.Column(
        "role_id", db.Integer, db.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    ),
    db.Column(
        "permission_id",
        db.Integer,
        db.ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Permission(db.Model):
    __tablename__ = "permissions"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    description = db.Column(db.String(180), nullable=False, default="")


class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    label = db.Column(db.String(80), nullable=False)
    is_system = db.Column(db.Boolean, nullable=False, default=False)
    permissions = db.relationship("Permission", secondary=role_permissions, lazy="selectin")


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(254), unique=True, index=True)
    display_name = db.Column(db.String(80), nullable=False)
    avatar_filename = db.Column(db.String(255))
    password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    totp_secret = db.Column(db.String(64))
    totp_enabled = db.Column(db.Boolean, nullable=False, default=False)
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True))
    last_login_at = db.Column(db.DateTime(timezone=True))
    password_changed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    roles = db.relationship("Role", secondary=user_roles, lazy="selectin")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password, method="scrypt")
        self.password_changed_at = utcnow()

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def has_permission(self, name: str) -> bool:
        return any(
            permission.name == name for role in self.roles for permission in role.permissions
        )

    def has_role(self, name: str) -> bool:
        return any(role.name == name for role in self.roles)


class UserSession(db.Model):
    __tablename__ = "user_sessions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_agent = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True))
    user = db.relationship("User")


class GatewayClient(db.Model):
    __tablename__ = "gateway_clients"
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    client_secret_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(240), nullable=False, default="")
    homepage_url = db.Column(db.String(500), nullable=False, default="")
    privacy_policy_url = db.Column(db.String(500), nullable=False, default="")
    service_terms_url = db.Column(db.String(500), nullable=False, default="")
    icon_url = db.Column(db.String(500), nullable=False, default="")
    redirect_uris_json = db.Column(db.Text, nullable=False, default="[]")
    scopes = db.Column(db.String(300), nullable=False, default="openid profile email avatar")
    requested_scopes = db.Column(db.String(300), nullable=False, default="openid")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    @property
    def redirect_uris(self) -> list[str]:
        try:
            value = json.loads(self.redirect_uris_json)
            return value if isinstance(value, list) else []
        except json.JSONDecodeError:
            return []

    @redirect_uris.setter
    def redirect_uris(self, value: list[str]) -> None:
        self.redirect_uris_json = json.dumps(value, ensure_ascii=False)

    def set_secret(self, secret: str) -> None:
        self.client_secret_hash = generate_password_hash(secret, method="scrypt")

    def check_secret(self, secret: str) -> bool:
        return check_password_hash(self.client_secret_hash, secret)


class UserClientConsent(db.Model):
    __tablename__ = "user_client_consents"
    __table_args__ = (db.UniqueConstraint("user_id", "client_id", name="uq_user_client_consent"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id = db.Column(
        db.String(64),
        db.ForeignKey("gateway_clients.client_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    granted_scopes = db.Column(db.String(300), nullable=False, default="openid")
    denied_scopes = db.Column(db.String(300), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    user = db.relationship("User")
    client = db.relationship("GatewayClient")


class AuthorizationGrant(db.Model):
    __tablename__ = "authorization_grants"
    id = db.Column(db.Integer, primary_key=True)
    code_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    client_id = db.Column(db.String(64), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    redirect_uri = db.Column(db.String(500), nullable=False)
    scope = db.Column(db.String(300), nullable=False)
    nonce = db.Column(db.String(180))
    code_challenge = db.Column(db.String(180), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    user = db.relationship("User")


class OAuthToken(db.Model):
    __tablename__ = "oauth_tokens"
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.String(64), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    access_token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    refresh_token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    scope = db.Column(db.String(300), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    refresh_expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    user = db.relationship("User")


class LoginLog(db.Model):
    __tablename__ = "login_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    identifier = db.Column(db.String(254), nullable=False, index=True)
    success = db.Column(db.Boolean, nullable=False)
    fingerprint = db.Column(db.String(64), nullable=False, index=True)
    client_ip_digest = db.Column(db.String(64), index=True)
    reason = db.Column(db.String(80), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    user = db.relationship("User")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    action = db.Column(db.String(100), nullable=False, index=True)
    target_type = db.Column(db.String(60), nullable=False)
    target_id = db.Column(db.String(80), nullable=False)
    summary = db.Column(db.String(500), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    actor = db.relationship("User")


class SiteSetting(db.Model):
    __tablename__ = "site_settings"
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text, nullable=False, default="")
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class MailProvider(db.Model):
    __tablename__ = "mail_providers"
    __table_args__ = (
        db.CheckConstraint("port BETWEEN 1 AND 65535", name="ck_mail_provider_port"),
        db.CheckConstraint(
            "security_mode IN ('ssl', 'starttls', 'plain')",
            name="ck_mail_provider_security_mode",
        ),
        db.CheckConstraint(
            "timeout_seconds BETWEEN 3 AND 60",
            name="ck_mail_provider_timeout",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    host = db.Column(db.String(255), nullable=False)
    port = db.Column(db.Integer, nullable=False, default=587)
    security_mode = db.Column(db.String(20), nullable=False, default="starttls")
    username = db.Column(db.String(254), nullable=False, default="")
    password_ciphertext = db.Column(db.Text, nullable=False, default="")
    sender_email = db.Column(db.String(254), nullable=False)
    sender_name = db.Column(db.String(100), nullable=False, default="baka网关")
    reply_to = db.Column(db.String(254), nullable=False, default="")
    timeout_seconds = db.Column(db.Integer, nullable=False, default=15)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False, index=True)
    last_tested_at = db.Column(db.DateTime(timezone=True))
    last_test_succeeded = db.Column(db.Boolean)
    last_test_error = db.Column(db.String(240), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    def set_password(self, password: str) -> None:
        from app.services.email_security import encrypt_smtp_password

        self.password_ciphertext = encrypt_smtp_password(password) if password else ""

    def get_password(self) -> str:
        from app.services.email_security import decrypt_smtp_password

        return decrypt_smtp_password(self.password_ciphertext) if self.password_ciphertext else ""


class MailTemplate(db.Model):
    __tablename__ = "mail_templates"
    __table_args__ = (
        db.CheckConstraint(
            "key IN ("
            "'smtp_test', "
            "'admin_email_verification', "
            "'registration', "
            "'account_email_verification', "
            "'change_email', "
            "'password_reset', "
            "'login_verification'"
            ")",
            name="ck_mail_template_key",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(60), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(150), nullable=False)
    body_html = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class PendingRegistration(db.Model):
    __tablename__ = "pending_registrations"

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    username = db.Column(db.String(50), nullable=False, index=True)
    display_name = db.Column(db.String(80), nullable=False)
    email_digest = db.Column(db.String(64), nullable=False, index=True)
    email_ciphertext = db.Column(db.Text, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    continuation_ciphertext = db.Column(db.Text, nullable=False, default="")
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    completed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def set_email(self, email: str) -> None:
        from app.services.email_security import encrypt_email_address, recipient_digest

        normalized = email.strip().lower()
        self.email_digest = recipient_digest(normalized)
        self.email_ciphertext = encrypt_email_address(normalized, "pending-registration")

    def get_email(self) -> str:
        from app.services.email_security import decrypt_email_address

        return decrypt_email_address(self.email_ciphertext, "pending-registration")

    def set_continuation(self, value: str) -> None:
        from app.services.email_security import encrypt_sensitive_value

        self.continuation_ciphertext = (
            encrypt_sensitive_value(value, "pending-registration-continuation") if value else ""
        )

    def get_continuation(self) -> str:
        from app.services.email_security import decrypt_sensitive_value

        return (
            decrypt_sensitive_value(
                self.continuation_ciphertext,
                "pending-registration-continuation",
            )
            if self.continuation_ciphertext
            else ""
        )


class EmailChallenge(db.Model):
    __tablename__ = "email_challenges"
    __table_args__ = (
        db.CheckConstraint(
            "purpose IN ('register', 'verify_email', 'change_email', 'password_reset', "
            "'login_verification')",
            name="ck_email_challenge_purpose",
        ),
        db.CheckConstraint("attempt_count >= 0", name="ck_email_challenge_attempt_count"),
        db.CheckConstraint("max_attempts BETWEEN 1 AND 20", name="ck_email_challenge_max_attempts"),
        db.Index(
            "ix_email_challenge_recipient_purpose_created",
            "recipient_digest",
            "purpose",
            "created_at",
        ),
        db.Index(
            "ix_email_challenge_fingerprint_created",
            "request_fingerprint",
            "created_at",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    purpose = db.Column(db.String(40), nullable=False, index=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    pending_registration_id = db.Column(
        db.Integer,
        db.ForeignKey("pending_registrations.id", ondelete="CASCADE"),
        index=True,
    )
    recipient_digest = db.Column(db.String(64), nullable=False, index=True)
    recipient_ciphertext = db.Column(db.Text, nullable=False)
    code_digest = db.Column(db.String(64), nullable=False)
    request_fingerprint = db.Column(db.String(64), nullable=False, default="", index=True)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=5)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    consumed_at = db.Column(db.DateTime(timezone=True))
    invalidated_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    user = db.relationship("User")
    pending_registration = db.relationship("PendingRegistration")

    def get_recipient(self) -> str:
        from app.services.email_security import decrypt_email_address

        return decrypt_email_address(self.recipient_ciphertext, "email-challenge")


class PendingEmailChange(db.Model):
    __tablename__ = "pending_email_changes"

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(64), unique=True, nullable=False)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    new_email_digest = db.Column(db.String(64), nullable=False, index=True)
    new_email_ciphertext = db.Column(db.Text, nullable=False)
    old_email_digest = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    consumed_at = db.Column(db.DateTime(timezone=True))
    invalidated_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    user = db.relationship("User", backref="pending_email_changes")

    def set_new_email(self, email: str) -> None:
        from app.services.email_security import encrypt_email_address, recipient_digest

        normalized = email.strip().lower()
        self.new_email_digest = recipient_digest(normalized)
        self.new_email_ciphertext = encrypt_email_address(normalized, "pending-email-change")

    def get_new_email(self) -> str:
        from app.services.email_security import decrypt_email_address

        return decrypt_email_address(self.new_email_ciphertext, "pending-email-change")
