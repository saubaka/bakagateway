from __future__ import annotations

from datetime import UTC, datetime

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.portal import portal_bp
from app.extensions import db
from app.forms import ChangeEmailRequestForm, EmptyForm, ProfileForm, TwoFactorForm
from app.models import (
    AuditLog,
    GatewayClient,
    LoginLog,
    OAuthToken,
    UserClientConsent,
    UserSession,
)
from app.security import generate_totp_secret
from app.services.auth import (
    administrator_exists,
    aware,
    current_gateway_session,
    record_audit,
    revoke_session,
)
from app.services.email_policy import effective_email_features
from app.services.oauth_permissions import (
    OPTIONAL_PERMISSION_DEFINITIONS,
    normalized_client_scopes,
    ordered_optional_scopes,
    save_user_consent,
)


def _active_sessions() -> list[UserSession]:
    return db.session.scalars(
        db.select(UserSession)
        .where(
            UserSession.user_id == current_user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(UTC),
        )
        .order_by(UserSession.last_seen_at.desc())
    ).all()


def _connected_clients() -> list[GatewayClient]:
    client_ids = set(
        db.session.scalars(
            db.select(OAuthToken.client_id).where(
                OAuthToken.user_id == current_user.id,
                OAuthToken.revoked_at.is_(None),
                OAuthToken.refresh_expires_at > datetime.now(UTC),
            )
        ).all()
    )
    if not client_ids:
        return []
    return db.session.scalars(
        db.select(GatewayClient)
        .where(
            GatewayClient.client_id.in_(client_ids),
            GatewayClient.is_active.is_(True),
        )
        .order_by(GatewayClient.name)
    ).all()


def _connected_platforms() -> list[dict]:
    consents = db.session.scalars(
        db.select(UserClientConsent)
        .where(UserClientConsent.user_id == current_user.id)
        .order_by(UserClientConsent.updated_at.desc())
    ).all()
    return [
        {
            "client": item.client,
            "consent": item,
            "permissions": [
                {
                    "scope": scope,
                    **OPTIONAL_PERMISSION_DEFINITIONS[scope],
                    "granted": scope in item.granted_scopes.split(),
                }
                for scope in ordered_optional_scopes(
                    set(item.granted_scopes.split()).union(item.denied_scopes.split())
                )
            ],
        }
        for item in consents
        if item.client is not None and item.client.is_active
    ]


def _activity_entries() -> list[dict]:
    entries = []
    login_items = db.session.scalars(
        db.select(LoginLog)
        .where(LoginLog.user_id == current_user.id)
        .order_by(LoginLog.created_at.desc())
        .limit(80)
    ).all()
    for item in login_items:
        entries.append(
            {
                "kind": "登录",
                "title": "登录成功" if item.success else "登录失败",
                "summary": (
                    "账号通过安全验证进入baka网关"
                    if item.success
                    else "凭据或二次验证码没有通过检查"
                ),
                "tone": "mint" if item.success else "pink",
                "created_at": item.created_at,
            }
        )
    labels = {
        "account.profile.update": ("修改个人资料", "资料与头像信息已经更新"),
        "account.email.update": ("更新当前邮箱", "邮箱已更新并等待重新验证"),
        "account.email.verification.send": ("发送邮箱验证码", "验证码已经发送到当前邮箱"),
        "account.email.verification.complete": ("验证当前邮箱", "当前邮箱已经完成真实验证码确认"),
        "account.email.change.send": ("发送换绑邮箱验证码", "验证码已经发送到新邮箱"),
        "account.email.change.complete": ("完成邮箱换绑", "新邮箱已经通过验证码确认并生效"),
        "account.password.recovery.request": ("申请找回密码", "已提交密码找回申请"),
        "account.password.recovery.send": ("发送找回密码验证码", "找回密码验证码发送结果已记录"),
        "account.password.recovery.verify": ("验证找回密码邮箱", "找回密码验证码已经确认"),
        "account.password.reset": ("重置登录密码", "已通过邮箱验证重置密码并撤销旧会话"),
        "account.register": ("完成注册", "账号已经通过邮箱验证创建"),
        "account.register.email.send": ("发送注册验证码", "注册验证码发送结果已记录"),
        "account.totp.enable": ("启用双重验证", "账号已开始使用动态验证码"),
        "account.totp.disable": ("关闭双重验证", "动态验证码保护已经关闭"),
        "session.revoke": ("踢出登录设备", "指定设备的服务器端会话已撤销"),
        "account.logout": ("退出登录", "主动退出当前登录设备"),
        "administrator.bootstrap": ("创建管理员", "完成baka网关首次管理员初始化"),
    }
    audit_items = db.session.scalars(
        db.select(AuditLog)
        .where(AuditLog.actor_id == current_user.id)
        .order_by(AuditLog.created_at.desc())
        .limit(120)
    ).all()
    for item in audit_items:
        title, fallback = labels.get(item.action, ("账号操作", item.action))
        entries.append(
            {
                "kind": "操作",
                "title": title,
                "summary": item.summary or fallback,
                "tone": "blue",
                "created_at": item.created_at,
            }
        )
    return sorted(
        entries,
        key=lambda item: aware(item["created_at"]) or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )[:120]


@portal_bp.get("/")
def home():
    if not administrator_exists():
        return redirect(url_for("auth.setup_administrator"))
    if current_user.is_authenticated:
        return redirect(url_for("portal.dashboard"))
    return redirect(url_for("auth.login", next=url_for("portal.dashboard")))


@portal_bp.get("/portal/")
@login_required
def dashboard():
    sessions = _active_sessions()
    clients = _connected_clients()
    recent = _activity_entries()[:5]
    return render_template(
        "portal/dashboard.html",
        sessions=sessions,
        clients=clients,
        recent=recent,
        empty_form=EmptyForm(),
    )


@portal_bp.get("/portal/profile/")
@login_required
def profile():
    return render_template(
        "portal/profile.html",
        profile_form=ProfileForm(obj=current_user),
        empty_form=EmptyForm(),
    )


@portal_bp.get("/portal/platforms/")
@login_required
def platforms():
    return render_template(
        "portal/platforms.html",
        platforms=_connected_platforms(),
        permission_form=EmptyForm(),
    )


@portal_bp.post("/portal/platforms/<string:client_id>/permissions/")
@login_required
def platform_permissions(client_id: str):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    client = db.session.scalar(
        db.select(GatewayClient).where(
            GatewayClient.client_id == client_id,
            GatewayClient.is_active.is_(True),
        )
    )
    consent = (
        db.session.scalar(
            db.select(UserClientConsent).where(
                UserClientConsent.user_id == current_user.id,
                UserClientConsent.client_id == client_id,
            )
        )
        if client is not None
        else None
    )
    if client is None or consent is None:
        abort(404)
    allowed_optional = ordered_optional_scopes(
        set(consent.granted_scopes.split()).union(consent.denied_scopes.split())
    )
    selected = [
        scope
        for scope in ordered_optional_scopes(request.form.getlist("permissions"))
        if scope in allowed_optional
    ]
    save_user_consent(
        current_user.id,
        client.client_id,
        allowed_optional,
        selected,
    )
    selected_set = set(selected)
    for token in db.session.scalars(
        db.select(OAuthToken).where(
            OAuthToken.user_id == current_user.id,
            OAuthToken.client_id == client.client_id,
            OAuthToken.revoked_at.is_(None),
        )
    ):
        current_optional = set(ordered_optional_scopes(token.scope))
        token.scope = normalized_client_scopes(current_optional.intersection(selected_set))
    record_audit(
        "oauth.permissions.update",
        "client",
        client.client_id,
        f"{client.name}：{normalized_client_scopes(selected)}",
    )
    db.session.commit()
    flash(f"{client.name}的读取权限已经更新。", "success")
    return redirect(url_for("portal.platforms"))


@portal_bp.get("/portal/devices/")
@login_required
def devices():
    return render_template(
        "portal/devices.html",
        sessions=_active_sessions(),
        current_session=current_gateway_session(),
        empty_form=EmptyForm(),
    )


@portal_bp.get("/portal/activity/")
@login_required
def activity():
    return render_template("portal/activity.html", entries=_activity_entries())


@portal_bp.get("/portal/security/")
@login_required
def security():
    if not current_user.totp_secret:
        current_user.totp_secret = generate_totp_secret()
        db.session.commit()
    return render_template(
        "portal/security.html",
        totp_form=TwoFactorForm(),
        empty_form=EmptyForm(),
        qr_version=current_user.totp_secret[-8:],
        change_email_form=ChangeEmailRequestForm(),
        email_verification_enabled=effective_email_features()["profile_verification"],
        email_change_enabled=effective_email_features()["profile_verification"],
    )


@portal_bp.post("/portal/sessions/<int:session_id>/revoke/")
@login_required
def revoke_device(session_id: int):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    item = db.session.get(UserSession, session_id)
    if item is None or item.user_id != current_user.id:
        abort(404)
    is_current = bool(
        current_gateway_session() and current_gateway_session().id == item.id
    )
    revoke_session(item)
    record_audit(
        "session.revoke",
        "session",
        str(item.id),
        f"踢出登录设备：{item.user_agent[:120] or '未知设备'}",
    )
    db.session.commit()
    if is_current:
        return redirect(url_for("auth.login"))
    return redirect(url_for("portal.devices"))


@portal_bp.get("/healthz")
def health():
    return jsonify(status="ok", version=current_app.config["APP_VERSION"])


@portal_bp.get("/readyz")
def ready():
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception:
        return jsonify(status="not-ready"), 503
    return jsonify(status="ready")
