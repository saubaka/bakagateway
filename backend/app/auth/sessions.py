import secrets
from datetime import timedelta

from flask import g, request, session

from ..extensions import db
from ..models import AuthSession, User
from .security import digest, now


def load(*, lock=False):
    token = session.get("sid")
    if not isinstance(token, str) or len(token) > 128:
        return None
    query = db.select(AuthSession).where(
        AuthSession.token_digest == digest(token),
        AuthSession.revoked_at.is_(None),
        AuthSession.expires_at > now(),
    )
    row = db.session.execute(query).scalar_one_or_none()
    if row and lock:
        # All authenticated writers take the user lock before any session lock.
        # Two devices may otherwise deadlock while revoking each other's rows.
        if row.user_id:
            db.session.execute(
                db.select(User)
                .where(User.id == row.user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).scalar_one_or_none()
        row = db.session.execute(
            query.with_for_update().execution_options(populate_existing=True)
        ).scalar_one_or_none()
    if (
        row
        and row.user_id
        and (not row.user or not row.user.is_active or row.user.auth_version != row.user_version)
    ):
        row = None
    if not row:
        session.clear()
    return row


def rotate(user=None, remember=False):
    old = load(lock=True)
    if old:
        old.revoked_at = now()
    token = secrets.token_urlsafe(32)
    row = AuthSession(
        token_digest=digest(token),
        browser_key=old.browser_key if old else secrets.token_urlsafe(32),
        csrf_token=secrets.token_urlsafe(32),
        user=user,
        user_version=user.auth_version if user else None,
        device_label=device_label(request.user_agent.string),
        ip_address=(request.remote_addr or "")[:64],
        last_seen_at=now(),
        expires_at=now() + timedelta(days=30)
        if user and remember
        else now() + timedelta(hours=8 if user else 2),
    )
    db.session.add(row)
    db.session.flush()
    session.clear()
    session["sid"] = token
    if remember:
        session.permanent = True
    g.auth_session = row
    return row


def payload(row):
    user = row.user
    return {
        "authenticated": user is not None,
        "user": None
        if not user
        else {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "email": user.email,
            "emailVerified": user.email_verified,
            "avatarUrl": f"/api/account/avatar/{user.avatar_key}" if user.avatar_key else None,
            "role": user.role,
        },
        "csrfToken": row.csrf_token,
    }


def current():
    row = load(lock=True) or rotate()
    touch(row)
    db.session.commit()
    return payload(row)


def touch(row):
    if (now() - row.last_seen_at).total_seconds() >= 60:
        row.last_seen_at = now()


def device_label(agent):
    browser = next(
        (
            name
            for needle, name in [
                ("Edg/", "Edge"),
                ("Firefox/", "Firefox"),
                ("Chrome/", "Chrome"),
                ("Safari/", "Safari"),
            ]
            if needle in agent
        ),
        "浏览器",
    )
    system = next(
        (
            name
            for needle, name in [
                ("Android", "Android"),
                ("iPhone", "iOS"),
                ("iPad", "iPadOS"),
                ("Windows", "Windows"),
                ("Macintosh", "macOS"),
                ("Linux", "Linux"),
            ]
            if needle in agent
        ),
        "未知系统",
    )
    return browser + " · " + system


def revoke_user(user):
    user.auth_version += 1
    db.session.execute(
        db.update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now())
    )
