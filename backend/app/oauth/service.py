import ipaddress
from urllib.parse import urlsplit

from flask import current_app, g

from ..auth.security import AuthError, now
from ..extensions import db
from ..models import User
from .models import OAuthClient, OAuthCode, OAuthConsent, OAuthToken

SCOPES = {"openid", "profile", "email", "offline_access"}


def web_url(value, *, optional=False):
    if not value and optional:
        return ""
    if (
        not isinstance(value, str)
        or len(value) > 512
        or any(ord(c) <= 32 for c in value)
        or "\\" in value
        or "%" in value
    ):
        raise ValueError("URL格式不可用")
    p = urlsplit(value)
    if not p.hostname or p.username or p.password or p.fragment or "*" in value:
        raise ValueError("URL格式不可用")
    if p.scheme == "https":
        return value
    try:
        local = p.hostname == "localhost" or ipaddress.ip_address(p.hostname).is_loopback
    except ValueError:
        local = p.hostname == "localhost"
    if current_app.config["BG_ENV"] != "production" and p.scheme == "http" and local:
        return value
    raise ValueError("需HTTPS，开发仅允许回环HTTP")


def lock_owner(row):
    db.session.execute(
        db.select(User)
        .where(User.id == row.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    client = db.session.execute(
        db.select(OAuthClient)
        .where(OAuthClient.id == row.client_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    return client


def valid_credential(row):
    user = db.session.get(User, row.user_id)
    client = db.session.get(OAuthClient, row.client_id)
    consent = db.session.get(OAuthConsent, row.consent_id)
    return bool(
        user
        and user.is_active
        and user.auth_version == row.user_version
        and client
        and client.active
        and client.version == row.client_version
        and consent
        and not consent.revoked_at
        and consent.version == row.consent_version
        and set(row.scope.split()) <= set(consent.scopes.split())
    )


def revoke_family(family):
    db.session.execute(
        db.update(OAuthToken)
        .where(OAuthToken.family_id == family, OAuthToken.revoked_at.is_(None))
        .values(revoked_at=now())
    )
    g.oauth_persist = True


def revoke_sessions(ids):
    if not ids:
        return
    for model in [OAuthToken, OAuthCode]:
        db.session.execute(
            db.update(model)
            .where(model.session_id.in_(ids), model.revoked_at.is_(None))
            .values(revoked_at=now())
        )


def revoke_connection(consent):
    consent.revoked_at = now()
    consent.version += 1
    for model in [OAuthToken, OAuthCode]:
        db.session.execute(
            db.update(model)
            .where(model.consent_id == consent.id, model.revoked_at.is_(None))
            .values(revoked_at=now())
        )


def claims(user, scope):
    result = {"sub": user.id}
    scopes = set(scope.split())
    if "profile" in scopes:
        result.update(name=user.nickname, nickname=user.nickname, preferred_username=user.username)
        if user.avatar_key:
            result["picture"] = current_app.config["BG_PUBLIC_URL"].rstrip("/") + "/oauth/picture"
    if "email" in scopes:
        result.update(email=user.email, email_verified=user.email_verified)
    return result


def consent_for(user_id, client_id):
    return db.session.scalar(
        db.select(OAuthConsent).where(
            OAuthConsent.user_id == user_id, OAuthConsent.client_id == client_id
        )
    )


def transaction(row, browser):
    if (
        not row
        or row.browser_key != browser.browser_key
        or row.consumed_at
        or row.expires_at <= now()
        or (row.user_id and row.user_id != browser.user_id)
    ):
        raise AuthError(
            "authorization_expired", "登录请求已过期或不属于此浏览器，请回到应用重新登录。", 400
        )
    return row
