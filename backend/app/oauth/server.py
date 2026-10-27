from datetime import timedelta

from authlib.integrations.flask_oauth2 import AuthorizationServer, ResourceProtector
from authlib.oauth2.rfc6749 import InvalidRequestError, OAuth2Request
from authlib.oauth2.rfc6749.grants import AuthorizationCodeGrant, RefreshTokenGrant
from authlib.oauth2.rfc6750 import BearerTokenValidator
from authlib.oauth2.rfc7009 import RevocationEndpoint
from authlib.oauth2.rfc7636 import CodeChallenge
from authlib.oauth2.rfc7662 import IntrospectionEndpoint
from authlib.oidc.core.grants import OpenIDCode
from flask import current_app, g, request

from ..auth.security import digest, now
from ..extensions import db
from .keys import private_key
from .models import OAuthClient, OAuthCode, OAuthToken
from .requests import CanonicalRequest
from .service import claims, lock_owner, revoke_family, valid_credential


class Server(AuthorizationServer):
    def create_oauth2_request(self, value):
        if isinstance(value, OAuth2Request):
            return value
        uri = current_app.config["BG_PUBLIC_URL"].rstrip("/") + request.path
        if request.query_string:
            uri += "?" + request.query_string.decode("ascii")
        return CanonicalRequest(
            request.method,
            uri,
            body=request.form.to_dict() if request.method == "POST" else None,
            headers=dict(request.headers),
        )


def query_client(identifier):
    row = db.session.get(OAuthClient, identifier)
    if row and row.active:
        g.oauth_client_version = row.version
        return row


def token_lookup(value, *, refresh=False):
    if not isinstance(value, str) or len(value) > 256:
        return None
    column = OAuthToken.refresh_digest if refresh else OAuthToken.access_digest
    row = db.session.scalar(db.select(OAuthToken).where(column == digest(value)))
    if row:
        lock_owner(row)
        row = db.session.scalar(
            db.select(OAuthToken)
            .where(column == digest(value))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    return row


class PKCE(CodeChallenge):
    SUPPORTED_CODE_CHALLENGE_METHOD = ("S256",)

    def validate_code_challenge(self, grant, redirect_uri):
        super().validate_code_challenge(grant, redirect_uri)
        p = grant.request.payload.data
        if not p.get("code_challenge") or p.get("code_challenge_method") != "S256":
            raise InvalidRequestError("S256 PKCE required")


class TokenGenerator:
    def generate_token(self, **kwargs):
        kwargs["include_refresh_token"] = (
            kwargs.get("include_refresh_token", True)
            and "offline_access" in (kwargs.get("scope") or "").split()
        )
        return super().generate_token(**kwargs)


class CodeGrant(TokenGenerator, AuthorizationCodeGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ("client_secret_basic",)

    def save_authorization_code(self, code, req):
        p = req.payload.data
        browser = g.auth_session
        consent = g.oauth_consent
        db.session.add(
            OAuthCode(
                code_digest=digest(code),
                user_id=req.user.id,
                user_version=req.user.auth_version,
                client_id=req.client.id,
                client_version=req.client.version,
                consent_id=consent.id,
                consent_version=consent.version,
                session_id=browser.id,
                scope=req.scope,
                redirect_uri=p["redirect_uri"],
                nonce=p.get("nonce"),
                nonce_digest=digest(p["nonce"]) if p.get("nonce") else None,
                code_challenge=p["code_challenge"],
                auth_time=int(browser.created_at.timestamp()),
                expires_at=now() + timedelta(seconds=60),
            )
        )

    def query_authorization_code(self, value, client):
        if not isinstance(value, str) or len(value) > 256:
            return None
        row = db.session.scalar(
            db.select(OAuthCode).where(
                OAuthCode.code_digest == digest(value), OAuthCode.client_id == client.id
            )
        )
        if not row:
            return None
        locked = lock_owner(row)
        if not locked or locked.version != g.oauth_client_version:
            return None
        row = db.session.scalar(
            db.select(OAuthCode)
            .where(OAuthCode.id == row.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row.consumed_at:
            revoke_family(row.family_id)
            return None
        if row.revoked_at or row.expires_at <= now() or not valid_credential(row):
            return None
        return row

    def delete_authorization_code(self, row):
        row.consumed_at = now()

    def authenticate_user(self, row):
        from ..models import User

        return db.session.get(User, row.user_id) if valid_credential(row) else None


class RefreshGrant(TokenGenerator, RefreshTokenGrant):
    INCLUDE_NEW_REFRESH_TOKEN = True
    TOKEN_ENDPOINT_AUTH_METHODS = ("client_secret_basic",)

    def authenticate_refresh_token(self, value):
        # Check ownership before locking/replay revocation; another client may
        # not use a stolen token value to revoke its owner's credential family.
        row = (
            db.session.scalar(
                db.select(OAuthToken).where(
                    OAuthToken.refresh_digest == digest(value),
                    OAuthToken.client_id == self.request.client.id,
                )
            )
            if len(value) <= 256
            else None
        )
        if not row:
            return None
        locked = lock_owner(row)
        row = db.session.scalar(
            db.select(OAuthToken)
            .where(OAuthToken.id == row.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not locked or locked.version != g.oauth_client_version:
            return None
        if row.refreshed_at:
            revoke_family(row.family_id)
            return None
        if row.revoked_at or row.refresh_expires_at <= now() or not valid_credential(row):
            return None
        return row

    def authenticate_user(self, row):
        return row.get_user() if valid_credential(row) else None

    def revoke_old_credential(self, row):
        row.refreshed_at = now()
        row.revoked_at = now()


def save_token(token, req):
    origin = req.authorization_code if req.authorization_code else req.refresh_token
    db.session.add(
        OAuthToken(
            access_digest=digest(token["access_token"]),
            refresh_digest=digest(token["refresh_token"]) if token.get("refresh_token") else None,
            family_id=origin.family_id,
            user_id=origin.user_id,
            client_id=origin.client_id,
            consent_id=origin.consent_id,
            session_id=origin.session_id,
            user_version=origin.user_version,
            client_version=origin.client_version,
            consent_version=origin.consent_version,
            scope=token["scope"],
            expires_at=now() + timedelta(seconds=token["expires_in"]),
            refresh_expires_at=origin.refresh_expires_at
            if isinstance(origin, OAuthToken)
            else now() + timedelta(days=30),
        )
    )


class OIDC(OpenIDCode):
    def resolve_client_private_key(self, client):
        return private_key()

    def get_client_algorithm(self, client):
        return "RS256"

    def get_encode_header(self, client):
        return {"alg": "RS256", "kid": private_key().kid}

    def get_client_claims(self, client):
        return {
            "iss": current_app.config["BG_PUBLIC_URL"].rstrip("/"),
            "aud": [client.id],
            "exp": int(now().timestamp()) + 600,
        }

    def exists_nonce(self, nonce, req):
        return bool(
            db.session.scalar(
                db.select(OAuthCode.id).where(
                    OAuthCode.client_id == req.payload.client_id,
                    OAuthCode.nonce_digest == digest(nonce),
                )
            )
        )

    def generate_user_info(self, user, scope):
        return claims(user, scope)


class Validator(BearerTokenValidator):
    def authenticate_token(self, value):
        return token_lookup(value)


class Resource(ResourceProtector):
    def acquire_token(self, scopes=None, **kwargs):
        value = CanonicalRequest(
            request.method,
            current_app.config["BG_PUBLIC_URL"].rstrip("/") + request.path,
            headers=request.headers,
        )
        return self.validate_request(
            request=value, scopes=[scopes] if isinstance(scopes, str) else scopes
        )


class Revoke(RevocationEndpoint):
    CLIENT_AUTH_METHODS = ("client_secret_basic",)

    def query_token(self, value, hint):
        # Filter before lock in token_lookup for cross-client isolation.
        return token_lookup(value) or token_lookup(value, refresh=True)

    def authenticate_token(self, req, client):
        self.check_params(req, client)
        value = req.form["token"]
        row = (
            db.session.scalar(
                db.select(OAuthToken).where(
                    OAuthToken.client_id == client.id,
                    db.or_(
                        OAuthToken.access_digest == digest(value),
                        OAuthToken.refresh_digest == digest(value),
                    ),
                )
            )
            if len(value) <= 256
            else None
        )
        if not row:
            return None
        locked = lock_owner(row)
        if not locked or not locked.active or locked.version != g.oauth_client_version:
            return None
        return row

    def revoke_token(self, row, req):
        revoke_family(row.family_id)


class Introspect(IntrospectionEndpoint):
    CLIENT_AUTH_METHODS = ("client_secret_basic",)

    def authenticate_token(self, req, client):
        self.check_params(req, client)
        value = req.form["token"]
        row = (
            db.session.scalar(
                db.select(OAuthToken).where(
                    OAuthToken.client_id == client.id,
                    db.or_(
                        OAuthToken.access_digest == digest(value),
                        OAuthToken.refresh_digest == digest(value),
                    ),
                )
            )
            if len(value) <= 256
            else None
        )
        if row:
            locked = lock_owner(row)
            if not locked or not locked.active or locked.version != g.oauth_client_version:
                return None
            db.session.refresh(row)
            g.oauth_introspection_refresh = row.refresh_digest == digest(value)
        return row

    def check_permission(self, token, client, req):
        return token.client_id == client.id

    def create_introspection_payload(self, row):
        if not row or row.is_revoked():
            return {"active": False}
        is_refresh = getattr(g, "oauth_introspection_refresh", False)
        expires = row.refresh_expires_at if is_refresh else row.expires_at
        if expires <= now() or (is_refresh and row.refreshed_at):
            return {"active": False}
        result = self.introspect_token(row)
        result["exp"] = int(expires.timestamp())
        if is_refresh:
            result.pop("token_type", None)
        return result

    def introspect_token(self, row):
        return {
            "active": True,
            "client_id": row.client_id,
            "token_type": "Bearer",
            "scope": row.scope,
            "sub": row.user_id,
            "aud": row.client_id,
            "iss": current_app.config["BG_PUBLIC_URL"].rstrip("/"),
            "iat": int(row.created_at.timestamp()),
            "exp": int(row.expires_at.timestamp()),
        }


def initialize(app):
    app.config.update(
        OAUTH2_SCOPES_SUPPORTED=["openid", "profile", "email", "offline_access"],
        OAUTH2_REFRESH_TOKEN_GENERATOR=True,
        OAUTH2_TOKEN_EXPIRES_IN={"authorization_code": 600, "refresh_token": 600},
    )
    server = Server(app, query_client=query_client, save_token=save_token)
    server.register_grant(CodeGrant, [PKCE(), OIDC()])
    server.register_grant(RefreshGrant)
    server.register_endpoint(Revoke)
    server.register_endpoint(Introspect)
    resource = Resource()
    resource.register_token_validator(Validator())
    app.extensions["bg_oauth"] = server
    app.extensions["bg_resource"] = resource
    return server
