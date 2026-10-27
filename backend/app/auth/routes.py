import hmac
import re
import secrets
from datetime import timedelta
from functools import wraps

from flask import Blueprint, current_app, g, request
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash

from ..extensions import db
from ..models import AuthSettings, EmailChallenge, MailConfiguration, User
from ..responses import failure, success
from . import mail, sessions
from .security import (
    AuthError,
    decrypt,
    email,
    encrypt,
    keyed,
    limit,
    now,
    password,
    require_json,
    safe_next,
    username,
)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def options():
    settings = db.session.get(AuthSettings, 1)
    admin = db.session.execute(
        db.select(User.id).where(User.role == "admin", User.is_active.is_(True)).limit(1)
    ).scalar()
    configured = db.session.get(MailConfiguration, 1) is not None
    return {
        "registrationOpen": bool(settings and settings.registration_open and admin and configured),
        "emailAvailable": configured,
    }


def csrf():
    row = sessions.load(lock=True)
    supplied = request.headers.get("X-CSRF-Token", "")
    if not row or not hmac.compare_digest(row.csrf_token.encode(), supplied.encode()):
        raise AuthError("csrf_failed", "会话已失效，请刷新后重试。", 403)
    g.auth_session = row
    sessions.touch(row)
    return row


def mutation(fn):
    @wraps(fn)
    def wrapped(**route_values):
        try:
            csrf()
            data = require_json()
            result = fn(data, **route_values)
            db.session.commit()
            return success(result)
        except AuthError as error:
            if error.persist:
                db.session.commit()
            else:
                db.session.rollback()
            response, status = failure(error.code, error.message, error.status)
            if error.retry_after:
                response.headers["Retry-After"] = str(error.retry_after)
            return response, status
        except IntegrityError:
            db.session.rollback()
            return failure("account_unavailable", "账号名或邮箱暂时不可用，请重新注册。", 409)

    return wrapped


def flow_view(row):
    data = decrypt(row.encrypted_data, "challenge")
    address = data["email"]
    local, domain = address.rsplit("@", 1)
    return {
        "purpose": row.purpose,
        "stage": "reset" if row.verified_at else "verify",
        "emailHint": local[:1] + "***@" + domain,
        "expiresAt": row.expires_at.isoformat(),
        "resendAt": row.resend_at.isoformat(),
        "next": data["next"],
    }


def active_flow(*, lock=False):
    browser = g.auth_session
    query = db.select(EmailChallenge).where(
        EmailChallenge.id == browser.flow_id, EmailChallenge.session_id == browser.id
    )
    if lock:
        query = query.with_for_update()
    row = db.session.execute(query).scalar_one_or_none()
    if not row or row.consumed_at or row.expires_at <= now() or row.attempts >= 5:
        raise AuthError("challenge_invalid", "验证流程已过期或不可用，请重新开始。")
    return row


def begin_flow(purpose, data, user=None):
    browser = g.auth_session
    recipient = data["email"]
    limit("mail-source", maximum=30, seconds=3600)
    limit("mail-recipient", recipient, maximum=6, seconds=3600)
    code = f"{secrets.randbelow(1000000):06d}"
    row = EmailChallenge(
        purpose=purpose,
        session_id=browser.id,
        user_id=user.id if user else None,
        user_version=user.auth_version if user else None,
        encrypted_data=encrypt(data, "challenge"),
        code_digest="",
        expires_at=now() + timedelta(minutes=10),
        resend_at=now() + timedelta(seconds=60),
    )
    db.session.add(row)
    db.session.flush()
    row.code_digest = keyed("email-code/v1/" + row.id + "/" + code)
    mail.send(recipient, code=code)
    if browser.flow_id:
        old = db.session.get(EmailChallenge, browser.flow_id)
        if old and not old.consumed_at:
            old.consumed_at = now()
    browser.flow_id = row.id
    return {"flow": flow_view(row)}


@bp.get("/session")
def session_info():
    return success(sessions.current())


@bp.get("/options")
def auth_options():
    return success(options())


@bp.get("/flow")
def flow_info():
    browser = sessions.load()
    if not browser:
        return success({"flow": None})
    g.auth_session = browser
    try:
        return success({"flow": flow_view(active_flow())})
    except AuthError:
        return success({"flow": None})


@bp.post("/login")
@mutation
def login(data):
    if g.auth_session.user_id:
        raise AuthError("already_authenticated", "请先退出当前账号再切换登录。", 409)
    account = data.get("account", "")
    secret = data.get("password", "")
    if (
        not isinstance(account, str)
        or not isinstance(secret, str)
        or len(account) > 254
        or len(secret) > 128
    ):
        raise AuthError("invalid_credentials", "账号或密码不正确。", 401)
    account = account.strip().lower()
    limit("login-source", maximum=120)
    user = db.session.execute(
        db.select(User).where(or_(User.username == account, User.email == account))
    ).scalar_one_or_none()
    limit("login-account", user.id if user else account)
    snapshot = user.password_hash if user else current_app.config["BG_DUMMY_HASH"]
    valid = check_password_hash(snapshot, secret)
    if not valid or not user or not user.is_active:
        raise AuthError("invalid_credentials", "账号或密码不正确。", 401)
    db.session.refresh(user, with_for_update=True)
    if user.password_hash != snapshot or not user.is_active:
        raise AuthError("invalid_credentials", "账号或密码不正确。", 401)
    if not isinstance(data.get("remember", False), bool):
        raise AuthError("invalid_request", "请求格式不正确。")
    row = sessions.rotate(user, data.get("remember", False))
    return {"session": sessions.payload(row), "next": safe_next(data.get("next"))}


@bp.post("/logout")
@mutation
def logout(data):
    return {"session": sessions.payload(sessions.rotate())}


@bp.post("/register")
@mutation
def register(data):
    if g.auth_session.user_id:
        raise AuthError("already_authenticated", "请先退出当前账号。", 409)
    if not options()["registrationOpen"]:
        raise AuthError("registration_closed", "注册暂未开放，请联系管理员。", 403)
    name = username(data.get("username"))
    address = email(data.get("email"))
    nickname = data.get("nickname", "").strip() if isinstance(data.get("nickname", ""), str) else ""
    if len(nickname) > 40:
        raise AuthError("invalid_request", "昵称不能超过40个字符。")
    limit("register-source", maximum=20, seconds=3600)
    if db.session.execute(
        db.select(User.id).where(or_(User.username == name, User.email == address))
    ).scalar():
        raise AuthError("account_unavailable", "账号名或邮箱暂时不可用。", 409)
    hashed = password(data.get("password"), data.get("confirmPassword"))
    return begin_flow(
        "register",
        {
            "username": name,
            "nickname": nickname or name,
            "email": address,
            "passwordHash": hashed,
            "next": safe_next(data.get("next")),
        },
    )


@bp.post("/forgot-password")
@mutation
def forgot(data):
    if g.auth_session.user_id:
        raise AuthError("already_authenticated", "请先退出当前账号再找回密码。", 409)
    address = email(data.get("email"))
    user = db.session.execute(
        db.select(User).where(User.email == address, User.is_active.is_(True))
    ).scalar_one_or_none()
    # Same message delivery and public flow for known/unknown addresses. A decoy
    # challenge cannot grant a reset because it has no user association.
    return begin_flow("reset", {"email": address, "next": safe_next(data.get("next"))}, user)


@bp.post("/resend")
@mutation
def resend(data):
    return resend_flow()


def resend_flow():
    row = active_flow(lock=True)
    if row.verified_at:
        raise AuthError("challenge_invalid", "验证码已使用，请继续设置密码。")
    if row.resend_at > now():
        raise AuthError(
            "rate_limited",
            "请等待倒计时结束后重发。",
            429,
            retry_after=max(1, int((row.resend_at - now()).total_seconds())),
        )
    if row.send_count >= 5:
        raise AuthError("rate_limited", "此流程发送次数已用完，请重新开始。", 429, retry_after=600)
    saved = decrypt(row.encrypted_data, "challenge")
    limit("mail-source", maximum=30, seconds=3600)
    limit("mail-recipient", saved["email"], maximum=6, seconds=3600)
    code = f"{secrets.randbelow(1000000):06d}"
    mail.send(saved["email"], code=code)
    row.code_digest = keyed("email-code/v1/" + row.id + "/" + code)
    row.attempts = 0
    row.send_count += 1
    row.resend_at = now() + timedelta(seconds=60)
    return {"flow": flow_view(row)}


@bp.post("/verify-email")
@mutation
def verify(data):
    row = active_flow(lock=True)
    if row.purpose not in {"register", "reset"}:
        raise AuthError("challenge_invalid", "请在个人中心完成邮箱更换。")
    code = data.get("code", "")
    if row.verified_at:
        raise AuthError("challenge_invalid", "验证码已使用，请继续设置密码。")
    row.attempts += 1
    valid = (
        isinstance(code, str)
        and bool(re.fullmatch(r"\d{6}", code, flags=re.ASCII))
        and hmac.compare_digest(row.code_digest, keyed("email-code/v1/" + row.id + "/" + code))
    )
    if not valid or (row.purpose == "reset" and not row.user_id):
        raise AuthError("challenge_invalid", "验证码不正确或已失效。", persist=True)
    if row.purpose == "reset":
        user = db.session.execute(
            db.select(User).where(User.id == row.user_id).with_for_update()
        ).scalar_one_or_none()
        if not user or not user.is_active or user.auth_version != row.user_version:
            raise AuthError("challenge_invalid", "验证流程已失效，请重新开始。", persist=True)
        row.verified_at = now()
        row.code_digest = keyed("used/" + row.id)
        return {"stage": "reset"}
    if not options()["registrationOpen"]:
        raise AuthError("registration_closed", "注册已关闭，请联系管理员。", 403)
    saved = decrypt(row.encrypted_data, "challenge")
    user = User(
        username=saved["username"],
        nickname=saved["nickname"],
        email=saved["email"],
        password_hash=saved["passwordHash"],
    )
    db.session.add(user)
    db.session.flush()
    row.consumed_at = now()
    browser = sessions.rotate(user)
    return {"session": sessions.payload(browser), "next": saved["next"]}


@bp.post("/reset-password")
@mutation
def reset(data):
    row = active_flow(lock=True)
    if row.purpose != "reset" or not row.verified_at or not row.user_id:
        raise AuthError("challenge_invalid", "请先完成邮箱验证。")
    user = db.session.execute(
        db.select(User).where(User.id == row.user_id).with_for_update()
    ).scalar_one_or_none()
    if not user or not user.is_active or user.auth_version != row.user_version:
        raise AuthError("challenge_invalid", "验证流程已失效，请重新开始。")
    hashed = password(data.get("password"), data.get("confirmPassword"))
    user.password_hash = hashed
    sessions.revoke_user(user)
    row.consumed_at = now()
    saved = decrypt(row.encrypted_data, "challenge")
    browser = sessions.rotate()
    return {"session": sessions.payload(browser), "next": saved["next"]}
