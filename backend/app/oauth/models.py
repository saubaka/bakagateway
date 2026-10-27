import hmac

from authlib.oauth2.rfc6749 import ClientMixin, TokenMixin
from authlib.oidc.core import AuthorizationCodeMixin

from ..auth.security import digest
from ..extensions import db
from ..models import now, uid


class OAuthClient(db.Model, ClientMixin):
    __tablename__ = "oauth_clients"
    id = db.Column(db.String(48), primary_key=True)
    secret_digest = db.Column(db.String(64), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    icon_key = db.Column(db.String(40))
    description = db.Column(db.String(240), nullable=False, default="")
    homepage = db.Column(db.String(512), nullable=False, default="")
    privacy_url = db.Column(db.String(512), nullable=False, default="")
    terms_url = db.Column(db.String(512), nullable=False, default="")
    redirect_uris = db.Column(db.JSON, nullable=False)
    scopes = db.Column(db.String(128), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)

    def get_client_id(self):
        return self.id

    def get_default_redirect_uri(self):
        return None

    def check_redirect_uri(self, value):
        return value in self.redirect_uris

    def get_allowed_scope(self, scope):
        value = scope or "openid"
        return value if set(value.split()) <= set(self.scopes.split()) else None

    def check_client_secret(self, value):
        return (
            isinstance(value, str)
            and len(value) <= 256
            and hmac.compare_digest(self.secret_digest, digest(value))
        )

    def check_endpoint_auth_method(self, method, endpoint):
        return method == "client_secret_basic"

    def check_response_type(self, value):
        return value == "code"

    def check_grant_type(self, value):
        return value in {"authorization_code", "refresh_token"}


class OAuthConsent(db.Model):
    __tablename__ = "oauth_consents"
    __table_args__ = (db.UniqueConstraint("user_id", "client_id", name="uq_oauth_consent_owner"),)
    id = db.Column(db.String(36), primary_key=True, default=uid)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id = db.Column(
        db.String(48),
        db.ForeignKey("oauth_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scopes = db.Column(db.String(128), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    revoked_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    last_used_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)


class OAuthTransaction(db.Model):
    __tablename__ = "oauth_transactions"
    id = db.Column(db.String(64), primary_key=True)
    browser_key = db.Column(db.String(64), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"))
    encrypted_data = db.Column(db.Text, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    consumed_at = db.Column(db.DateTime(timezone=True))


class OAuthCode(db.Model, AuthorizationCodeMixin):
    __tablename__ = "oauth_codes"
    __table_args__ = (db.UniqueConstraint("client_id", "nonce_digest", name="uq_oauth_code_nonce"),)
    id = db.Column(db.String(36), primary_key=True, default=uid)
    code_digest = db.Column(db.String(64), unique=True, nullable=False)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_id = db.Column(
        db.String(48), db.ForeignKey("oauth_clients.id", ondelete="CASCADE"), nullable=False
    )
    consent_id = db.Column(
        db.String(36), db.ForeignKey("oauth_consents.id", ondelete="CASCADE"), nullable=False
    )
    session_id = db.Column(db.String(36), db.ForeignKey("auth_sessions.id", ondelete="SET NULL"))
    user_version = db.Column(db.Integer, nullable=False)
    client_version = db.Column(db.Integer, nullable=False)
    consent_version = db.Column(db.Integer, nullable=False)
    family_id = db.Column(db.String(36), nullable=False, index=True, default=uid)
    redirect_uri = db.Column(db.String(512), nullable=False)
    scope = db.Column(db.String(128), nullable=False)
    nonce = db.Column(db.String(256))
    nonce_digest = db.Column(db.String(64))
    code_challenge = db.Column(db.String(128), nullable=False)
    code_challenge_method = db.Column(db.String(8), nullable=False, default="S256")
    auth_time = db.Column(db.Integer, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    consumed_at = db.Column(db.DateTime(timezone=True))
    revoked_at = db.Column(db.DateTime(timezone=True))

    def get_redirect_uri(self):
        return self.redirect_uri

    def get_scope(self):
        return self.scope

    def get_nonce(self):
        return self.nonce

    def get_auth_time(self):
        return self.auth_time


class OAuthToken(db.Model, TokenMixin):
    __tablename__ = "oauth_tokens"
    id = db.Column(db.String(36), primary_key=True, default=uid)
    access_digest = db.Column(db.String(64), unique=True, nullable=False)
    refresh_digest = db.Column(db.String(64), unique=True)
    family_id = db.Column(db.String(36), nullable=False, index=True)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id = db.Column(
        db.String(48),
        db.ForeignKey("oauth_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    consent_id = db.Column(
        db.String(36), db.ForeignKey("oauth_consents.id", ondelete="CASCADE"), nullable=False
    )
    session_id = db.Column(db.String(36), db.ForeignKey("auth_sessions.id", ondelete="SET NULL"))
    user_version = db.Column(db.Integer, nullable=False)
    client_version = db.Column(db.Integer, nullable=False)
    consent_version = db.Column(db.Integer, nullable=False)
    scope = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    refresh_expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    revoked_at = db.Column(db.DateTime(timezone=True))
    refreshed_at = db.Column(db.DateTime(timezone=True))

    def check_client(self, client):
        return self.client_id == client.id

    def get_scope(self):
        return self.scope

    def get_expires_in(self):
        return max(0, int((self.expires_at - now()).total_seconds()))

    def is_expired(self):
        return self.expires_at <= now()

    def is_revoked(self):
        from .service import valid_credential

        return bool(self.revoked_at) or not valid_credential(self)

    def get_user(self):
        from ..models import User

        return db.session.get(User, self.user_id)

    def get_client(self):
        return db.session.get(OAuthClient, self.client_id)
