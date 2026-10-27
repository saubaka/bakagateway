import uuid
from datetime import UTC, datetime

from .extensions import db


class PlatformInstallation(db.Model):
    __tablename__ = "platform_installation"
    id = db.Column(db.Integer, primary_key=True)
    schema_label = db.Column(db.String(64), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(UTC)


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (db.CheckConstraint("role IN ('user','admin')", name="ck_user_role"),)
    id = db.Column(db.String(36), primary_key=True, default=uid)
    username = db.Column(db.String(32), unique=True, nullable=False)
    nickname = db.Column(db.String(40), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(16), nullable=False, default="user")
    email_verified = db.Column(db.Boolean, nullable=False, default=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    auth_version = db.Column(db.Integer, nullable=False, default=1)
    avatar_key = db.Column(db.String(40))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)


class AuthSession(db.Model):
    __tablename__ = "auth_sessions"
    id = db.Column(db.String(36), primary_key=True, default=uid)
    token_digest = db.Column(db.String(64), unique=True, nullable=False)
    csrf_token = db.Column(db.String(64), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    user_version = db.Column(db.Integer)
    browser_key = db.Column(
        db.String(64), nullable=False, default=lambda: __import__("secrets").token_urlsafe(32)
    )
    flow_id = db.Column(db.String(36))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    device_label = db.Column(db.String(80), nullable=False, default="未知设备")
    ip_address = db.Column(db.String(64), nullable=False, default="")
    revoked_at = db.Column(db.DateTime(timezone=True), index=True)
    user = db.relationship(User)


class EmailChallenge(db.Model):
    __tablename__ = "email_challenges"
    __table_args__ = (
        db.CheckConstraint(
            "purpose IN ('register','reset','email-change')", name="ck_challenge_purpose"
        ),
    )
    id = db.Column(db.String(36), primary_key=True, default=uid)
    session_id = db.Column(
        db.String(36),
        db.ForeignKey("auth_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purpose = db.Column(db.String(16), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"))
    user_version = db.Column(db.Integer)
    encrypted_data = db.Column(db.Text, nullable=False)
    code_digest = db.Column(db.String(64), nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    send_count = db.Column(db.Integer, nullable=False, default=1)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    resend_at = db.Column(db.DateTime(timezone=True), nullable=False)
    verified_at = db.Column(db.DateTime(timezone=True))
    consumed_at = db.Column(db.DateTime(timezone=True))


class MailConfiguration(db.Model):
    __tablename__ = "mail_configuration"
    version = db.Column(db.Integer, nullable=False, default=1)
    id = db.Column(db.Integer, primary_key=True)
    encrypted_data = db.Column(db.Text, nullable=False)


class AuthSettings(db.Model):
    __tablename__ = "auth_settings"
    id = db.Column(db.Integer, primary_key=True)
    registration_open = db.Column(db.Boolean, nullable=False, default=False)


class AuthRate(db.Model):
    __tablename__ = "auth_rates"
    bucket = db.Column(db.String(64), primary_key=True)
    count = db.Column(db.Integer, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)


class SiteSettings(db.Model):
    __tablename__ = "site_settings"
    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(60), nullable=False, default="baka 身份平台")
    description = db.Column(db.String(200), nullable=False, default="一个账号，连接你的应用。")
    support_email = db.Column(db.String(254), nullable=False, default="")
    version = db.Column(db.Integer, nullable=False, default=1)


class AdminAudit(db.Model):
    __tablename__ = "admin_audit"
    id = db.Column(db.String(36), primary_key=True, default=uid)
    actor_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    actor_name = db.Column(db.String(32), nullable=False)
    action = db.Column(db.String(40), nullable=False, index=True)
    target_id = db.Column(db.String(48), nullable=False, default="")
    summary = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now, index=True)
