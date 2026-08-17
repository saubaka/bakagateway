from __future__ import annotations

from datetime import UTC, datetime, timedelta

from flask import current_app, request, session
from flask_login import login_user
from sqlalchemy import or_

from app.extensions import db
from app.models import (
    AuditLog,
    AuthorizationGrant,
    LoginLog,
    OAuthToken,
    Role,
    User,
    UserSession,
)
from app.security import hash_token, new_token, request_fingerprint


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def establish_session(user: User, remember: bool = False) -> UserSession:
    raw = new_token(36)
    ttl = (
        current_app.config["PERSISTENT_SESSION_TTL"]
        if remember
        else current_app.config["SESSION_TTL"]
    )
    item = UserSession(
        user=user,
        token_hash=hash_token(raw),
        user_agent=request.user_agent.string[:255],
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
    )
    db.session.add(item)
    db.session.flush()
    session.clear()
    session.permanent = remember
    login_user(user, remember=False, fresh=True)
    session["gateway_session"] = raw
    session["gateway_session_id"] = item.id
    return item


def current_gateway_session() -> UserSession | None:
    raw = session.get("gateway_session")
    item_id = session.get("gateway_session_id")
    if not raw or not item_id:
        return None
    item = db.session.get(UserSession, item_id)
    if (
        item is None
        or item.token_hash != hash_token(raw)
        or item.revoked_at is not None
        or aware(item.expires_at) <= datetime.now(UTC)
    ):
        return None
    return item


def revoke_session(item: UserSession) -> None:
    item.revoked_at = datetime.now(UTC)


def record_login(identifier: str, user: User | None, success: bool, reason: str) -> None:
    db.session.add(
        LoginLog(
            user=user,
            identifier=identifier[:254],
            success=success,
            fingerprint=request_fingerprint("login"),
            reason=reason[:80],
        )
    )


def recent_login_failures(identifier: str) -> int:
    normalized = identifier.strip().lower()
    since = datetime.now(UTC) - timedelta(seconds=current_app.config["LOGIN_WINDOW_SECONDS"])
    user = db.session.scalar(
        db.select(User).where(
            or_(User.username == normalized, User.email == normalized)
        )
    )
    if user is not None:
        password_changed_at = aware(user.password_changed_at)
        if password_changed_at is not None and password_changed_at > since:
            since = password_changed_at
        latest_success = db.session.scalar(
            db.select(db.func.max(LoginLog.created_at)).where(
                LoginLog.user_id == user.id,
                LoginLog.success.is_(True),
            )
        )
        latest_success = aware(latest_success)
        if latest_success is not None and latest_success > since:
            since = latest_success
        identity_filter = LoginLog.user_id == user.id
    else:
        identity_filter = LoginLog.identifier == normalized
    return (
        db.session.scalar(
            db.select(db.func.count(LoginLog.id)).where(
                identity_filter,
                LoginLog.success.is_(False),
                LoginLog.created_at >= since,
            )
        )
        or 0
    )


def record_audit(action: str, target_type: str, target_id: str, summary: str = "") -> None:
    from flask_login import current_user

    db.session.add(
        AuditLog(
            actor=current_user if current_user.is_authenticated else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            summary=summary[:500],
        )
    )


def administrator_exists() -> bool:
    return (
        db.session.scalar(
            db.select(User.id)
            .join(User.roles)
            .where(Role.name == "administrator", User.status == "active")
            .limit(1)
        )
        is not None
    )


def active_administrator_count(*, excluding_user_id: int | None = None) -> int:
    query = (
        db.select(db.func.count(db.distinct(User.id)))
        .join(User.roles)
        .where(Role.name == "administrator", User.status == "active")
    )
    if excluding_user_id is not None:
        query = query.where(User.id != excluding_user_id)
    return db.session.scalar(query) or 0


def revoke_user_access(user_id: int) -> None:
    now = datetime.now(UTC)
    db.session.execute(
        db.update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.session.execute(
        db.update(OAuthToken)
        .where(OAuthToken.user_id == user_id, OAuthToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.session.execute(
        db.delete(AuthorizationGrant).where(
            AuthorizationGrant.user_id == user_id,
            AuthorizationGrant.used_at.is_(None),
        )
    )


def revoke_client_access(client_id: str) -> None:
    now = datetime.now(UTC)
    db.session.execute(
        db.update(OAuthToken)
        .where(OAuthToken.client_id == client_id, OAuthToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.session.execute(
        db.delete(AuthorizationGrant).where(
            AuthorizationGrant.client_id == client_id,
            AuthorizationGrant.used_at.is_(None),
        )
    )


def seed_roles() -> tuple[Role, Role]:
    from app.models import Permission

    definitions = {
        "portal.access": "访问个人应用门户",
        "admin.access": "访问网关管理后台",
        "users.manage": "管理账号",
        "clients.manage": "管理接入应用",
        "security.audit": "查看安全与审计记录",
    }
    permissions = {}
    for name, description in definitions.items():
        item = db.session.scalar(db.select(Permission).where(Permission.name == name))
        if item is None:
            item = Permission(name=name, description=description)
            db.session.add(item)
        permissions[name] = item
    member = db.session.scalar(db.select(Role).where(Role.name == "member"))
    if member is None:
        member = Role(name="member", label="普通用户", is_system=True)
        db.session.add(member)
    member.permissions = [permissions["portal.access"]]
    administrator = db.session.scalar(db.select(Role).where(Role.name == "administrator"))
    if administrator is None:
        administrator = Role(name="administrator", label="管理员", is_system=True)
        db.session.add(administrator)
    administrator.permissions = list(permissions.values())
    db.session.flush()
    return member, administrator
