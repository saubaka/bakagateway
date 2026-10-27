import hmac
import re

from flask import Blueprint, g, send_file
from sqlalchemy import func
from werkzeug.security import check_password_hash

from ..auth import mail, sessions
from ..auth.routes import active_flow, begin_flow, flow_view, mutation, resend_flow
from ..auth.security import AuthError, decrypt, email, keyed, limit, now, password
from ..extensions import db
from ..models import AuthSession, User
from ..responses import success
from . import avatars

bp = Blueprint("account", __name__, url_prefix="/api/account")


@bp.before_request
def authenticate():
    row = sessions.load(lock=True)
    if not row or not row.user_id:
        raise AuthError("authentication_required", "登录已过期，请重新登录。", 401)
    g.auth_session = row


def user():
    return g.auth_session.user


def result_user():
    return {"user": sessions.payload(g.auth_session)["user"]}


def read_result(value):
    sessions.touch(g.auth_session)
    db.session.commit()
    return success(value)


def reauthenticate(data):
    limit("account-sensitive", user().id, maximum=6)
    value = data.get("currentPassword", "")
    if (
        not isinstance(value, str)
        or len(value) > 128
        or not check_password_hash(user().password_hash, value)
    ):
        raise AuthError("invalid_credentials", "当前密码不正确。", 401)


def email_flow():
    row = active_flow(lock=True)
    if (
        row.purpose != "email-change"
        or row.user_id != user().id
        or row.user_version != user().auth_version
    ):
        raise AuthError("challenge_invalid", "邮箱更换流程已失效，请重新开始。")
    return row


@bp.get("/profile")
def profile():
    return read_result(result_user())


@bp.post("/profile")
@mutation
def edit_profile(data):
    if (
        set(data) != {"nickname"}
        or not isinstance(data["nickname"], str)
        or not 1 <= len(data["nickname"].strip()) <= 40
    ):
        raise AuthError("invalid_request", "昵称须为1–40个字符，账号名和身份编号不能修改。")
    user().nickname = data["nickname"].strip()
    return result_user()


@bp.post("/avatar")
@mutation
def upload_avatar(data):
    limit("avatar-upload", user().id, maximum=20)
    user().avatar_key = avatars.save(data.get("image"))
    return result_user()


@bp.post("/avatar/remove")
@mutation
def remove_avatar(data):
    user().avatar_key = None
    return result_user()


@bp.get("/avatar/<key>")
def get_avatar(key):
    if not avatars.KEY.fullmatch(key) or user().avatar_key != key:
        raise AuthError("not_found", "头像不存在。", 404)
    path = avatars.directory() / key
    if not path.is_file() or path.is_symlink():
        raise AuthError("not_found", "头像不存在。", 404)
    sessions.touch(g.auth_session)
    db.session.commit()
    return send_file(path, mimetype="image/png", conditional=False, etag=False, max_age=0)


@bp.post("/password")
@mutation
def change_password(data):
    reauthenticate(data)
    hashed = password(data.get("password"), data.get("confirmPassword"))
    target = user()
    target.password_hash = hashed
    sessions.revoke_user(target)
    return {"session": sessions.payload(sessions.rotate())}


@bp.get("/email/flow")
def current_email_flow():
    try:
        value = flow_view(email_flow())
    except AuthError:
        value = None
    return read_result({"flow": value})


@bp.post("/email/start")
@mutation
def start_email(data):
    reauthenticate(data)
    address = email(data.get("email"))
    if address == user().email or db.session.scalar(
        db.select(User.id).where(User.email == address)
    ):
        raise AuthError("account_unavailable", "此邮箱暂时不可用，请使用其他邮箱。", 409)
    return begin_flow("email-change", {"email": address, "next": "/account/security"}, user())


@bp.post("/email/resend")
@mutation
def resend_email(data):
    email_flow()
    return resend_flow()


@bp.post("/email/verify")
@mutation
def verify_email(data):
    row = email_flow()
    value = data.get("code", "")
    row.attempts += 1
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[0-9]{6}", value)
        or not hmac.compare_digest(row.code_digest, keyed("email-code/v1/" + row.id + "/" + value))
    ):
        raise AuthError("challenge_invalid", "验证码不正确或已失效。", persist=True)
    saved = decrypt(row.encrypted_data, "challenge")
    if db.session.scalar(db.select(User.id).where(User.email == saved["email"])):
        raise AuthError("account_unavailable", "此邮箱暂时不可用，请重新开始。", 409)
    mail.send(user().email, notice=True)
    target = user()
    target.email = saved["email"]
    target.email_verified = True
    row.consumed_at = now()
    sessions.revoke_user(target)
    return {"session": sessions.payload(sessions.rotate())}


def active_sessions():
    return db.select(AuthSession).where(
        AuthSession.user_id == user().id,
        AuthSession.user_version == user().auth_version,
        AuthSession.revoked_at.is_(None),
        AuthSession.expires_at > now(),
    )


@bp.get("/sessions")
def devices():
    query = active_sessions()
    total = db.session.scalar(db.select(func.count()).select_from(query.subquery()))
    rows = db.session.scalars(query.order_by(AuthSession.created_at.desc()).limit(100)).all()
    sessions.touch(g.auth_session)
    items = [
        {
            "id": r.id,
            "label": r.device_label,
            "ipAddress": r.ip_address,
            "createdAt": r.created_at.isoformat(),
            "lastSeenAt": r.last_seen_at.isoformat(),
            "expiresAt": r.expires_at.isoformat(),
            "current": r.id == g.auth_session.id,
        }
        for r in rows
    ]
    return read_result({"items": items, "total": total})


@bp.post("/sessions/<session_id>/revoke")
@mutation
def revoke_device(data, session_id):
    target = db.session.scalar(active_sessions().where(AuthSession.id == session_id))
    if not target:
        raise AuthError("not_found", "设备不存在或已退出。", 404)
    from ..oauth.service import revoke_sessions

    revoke_sessions([target.id])
    target.revoked_at = now()
    if target.id == g.auth_session.id:
        return {"revoked": True, "session": sessions.payload(sessions.rotate())}
    return {"revoked": True}


@bp.post("/sessions/revoke-others")
@mutation
def revoke_others(data):
    from ..oauth.service import revoke_sessions

    ids = list(
        db.session.scalars(
            db.select(AuthSession.id).where(
                AuthSession.user_id == user().id,
                AuthSession.id != g.auth_session.id,
                AuthSession.revoked_at.is_(None),
            )
        )
    )
    revoke_sessions(ids)
    db.session.execute(
        db.update(AuthSession)
        .where(
            AuthSession.user_id == user().id,
            AuthSession.id != g.auth_session.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=now())
    )
    return {"revoked": True}


@bp.get("/connections")
def connections():
    from ..oauth.models import OAuthClient, OAuthConsent

    rows = db.session.execute(
        db.select(OAuthConsent, OAuthClient)
        .join(OAuthClient, OAuthConsent.client_id == OAuthClient.id)
        .where(OAuthConsent.user_id == user().id, OAuthConsent.revoked_at.is_(None))
    ).all()
    return read_result(
        {
            "integrationAvailable": True,
            "items": [
                {
                    "id": c.id,
                    "name": a.name,
                    "description": a.description,
                    "homepage": a.homepage,
                    "scopes": c.scopes.split(),
                    "createdAt": c.created_at.isoformat(),
                    "lastUsedAt": c.last_used_at.isoformat(),
                    "active": a.active,
                }
                for c, a in rows
            ],
        }
    )


@bp.post("/connections/<connection_id>/revoke")
@mutation
def revoke_app(data, connection_id):
    from ..oauth.models import OAuthConsent
    from ..oauth.service import revoke_connection

    row = db.session.scalar(
        db.select(OAuthConsent).where(
            OAuthConsent.id == connection_id,
            OAuthConsent.user_id == user().id,
            OAuthConsent.revoked_at.is_(None),
        )
    )
    if not row:
        raise AuthError("not_found", "连接不存在或已撤销。", 404)
    revoke_connection(row)
    return {"revoked": True}
