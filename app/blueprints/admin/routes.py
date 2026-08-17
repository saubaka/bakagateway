from __future__ import annotations

import json
from datetime import UTC, datetime

from flask import abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user

from app.blueprints.admin import admin_bp
from app.extensions import db
from app.forms import (
    AdminEmailVerificationForm,
    ClientForm,
    DialogAppearanceForm,
    EmailPolicyForm,
    EmptyForm,
    InterfaceAppearanceForm,
    MailProviderForm,
    MailTemplateForm,
    MailTestForm,
    TransitionSettingsForm,
    UserAdminForm,
)
from app.models import (
    AuditLog,
    EmailChallenge,
    GatewayClient,
    LoginLog,
    MailProvider,
    MailTemplate,
    Role,
    User,
    UserSession,
)
from app.security import admin_required, new_token, request_fingerprint
from app.services.appearance import (
    DIALOG_SHADOW_CHOICES,
    DIALOG_SHADOW_VALUES,
    DIALOG_STYLE_CHOICES,
    DIALOG_STYLE_VALUES,
    GLOBAL_FONT_CHOICES,
    GLOBAL_FONT_VALUES,
    PAGE_TRANSITION_CHOICES,
    PAGE_TRANSITION_VALUES,
    load_footer_content,
    load_theme_settings,
    save_footer_content,
    set_setting,
)
from app.services.auth import (
    active_administrator_count,
    aware,
    record_audit,
    revoke_client_access,
    revoke_user_access,
)
from app.services.email_policy import (
    EmailFeaturePolicy,
    email_policy_readiness,
    load_email_policy,
    save_email_policy,
)
from app.services.email_security import (
    ChallengeRateLimited,
    consume_email_challenge,
    issue_email_challenge,
    recipient_digest,
)
from app.services.email_templates import (
    ensure_default_mail_templates,
    list_mail_templates,
    reset_mail_template,
    sample_template_variables,
    template_definition,
    template_is_custom,
    template_variables,
    upgrade_legacy_mail_templates,
)
from app.services.mail_delivery import (
    MailDeliveryError,
    ensure_default_mail_provider,
    is_loopback_smtp_host,
    send_mail_provider_test,
    send_verification_code,
    set_default_mail_provider,
    test_mail_provider_connection,
)
from app.services.oauth_permissions import normalized_client_scopes


@admin_bp.before_request
def protect_admin():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if not current_user.has_permission("admin.access"):
        abort(403)
    return None


@admin_bp.get("/")
@admin_required
def dashboard():
    stats = {
        "users": db.session.scalar(db.select(db.func.count(User.id))) or 0,
        "clients": db.session.scalar(db.select(db.func.count(GatewayClient.id))) or 0,
        "sessions": db.session.scalar(
            db.select(db.func.count(UserSession.id)).where(UserSession.revoked_at.is_(None))
        )
        or 0,
        "failures": db.session.scalar(
            db.select(db.func.count(LoginLog.id)).where(LoginLog.success.is_(False))
        )
        or 0,
    }
    recent = db.session.scalars(
        db.select(AuditLog).order_by(AuditLog.created_at.desc()).limit(8)
    ).all()
    return render_template("admin/dashboard.html", stats=stats, recent=recent)


@admin_bp.get("/users/")
@admin_required
def users():
    items = db.session.scalars(db.select(User).order_by(User.created_at.desc())).all()
    return render_template("admin/users.html", users=items)


@admin_bp.route("/users/<int:user_id>/", methods=["GET", "POST"])
@admin_required
def user_detail(user_id: int):
    user = db.get_or_404(User, user_id)
    form = UserAdminForm()
    if request.method == "GET":
        form.status.data = user.status
        form.role.data = "administrator" if user.has_role("administrator") else "member"
    if form.validate_on_submit():
        removes_active_administrator = (
            user.is_active
            and user.has_role("administrator")
            and (form.status.data != "active" or form.role.data != "administrator")
        )
        if (
            removes_active_administrator
            and active_administrator_count(excluding_user_id=user.id) == 0
        ):
            form.role.errors.append("必须至少保留一位可用的管理员。")
        elif user.id == current_user.id and form.status.data != "active":
            form.status.errors.append("不能停用当前登录的管理员。")
        else:
            role = db.session.scalar(db.select(Role).where(Role.name == form.role.data))
            user.status = form.status.data
            user.roles = [role] if role else []
            password_changed = bool(form.new_password.data)
            if password_changed:
                user.set_password(form.new_password.data)
                user.failed_attempts = 0
                user.locked_until = None
            if user.status != "active" or password_changed:
                revoke_user_access(user.id)
            record_audit(
                "admin.user.update",
                "user",
                str(user.id),
                (f"status={user.status};role={form.role.data};password_changed={password_changed}"),
            )
            db.session.commit()
            flash("账号设置已经保存。", "success")
            return redirect(url_for("admin.user_detail", user_id=user.id))
    return render_template("admin/user_detail.html", user=user, form=form)


@admin_bp.get("/clients/")
@admin_required
def clients():
    items = db.session.scalars(
        db.select(GatewayClient).order_by(GatewayClient.created_at.desc())
    ).all()
    return render_template("admin/clients.html", clients=items, empty_form=EmptyForm())


def _clean_redirect_uris(raw: str) -> list[str]:
    values = []
    for line in raw.splitlines():
        value = line.strip()
        if not value:
            continue
        if not (value.startswith("https://") or value.startswith("http://127.0.0.1")):
            raise ValueError("回调地址必须使用HTTPS；本机127.0.0.1可以使用HTTP。")
        values.append(value)
    if not values:
        raise ValueError("至少填写一个回调地址。")
    return list(dict.fromkeys(values))


def _client_scopes(form: ClientForm) -> str:
    permission_fields = {
        "allow_profile": "profile",
        "allow_email": "email",
        "allow_avatar": "avatar",
    }
    if "permissions_present" in request.form:
        selected = [
            scope for field, scope in permission_fields.items() if bool(getattr(form, field).data)
        ]
        return normalized_client_scopes(selected)
    legacy = set((form.scopes.data or "").split())
    return normalized_client_scopes(legacy)


@admin_bp.route("/clients/new/", methods=["GET", "POST"])
@admin_required
def client_new():
    form = ClientForm()
    if form.validate_on_submit():
        try:
            redirect_uris = _clean_redirect_uris(form.redirect_uris.data)
        except ValueError as error:
            form.redirect_uris.errors.append(str(error))
        else:
            raw_secret = new_token(32)
            item = GatewayClient(
                client_id=new_token(18),
                name=form.name.data.strip(),
                description=form.description.data.strip(),
                homepage_url=form.homepage_url.data.strip(),
                privacy_policy_url=form.privacy_policy_url.data.strip(),
                service_terms_url=form.service_terms_url.data.strip(),
                icon_url=form.icon_url.data.strip(),
                scopes=_client_scopes(form),
                is_active=bool(form.is_active.data),
            )
            item.redirect_uris = redirect_uris
            item.set_secret(raw_secret)
            db.session.add(item)
            db.session.flush()
            record_audit("admin.client.create", "client", item.client_id, item.name)
            db.session.commit()
            session["new_client_secret"] = raw_secret
            flash("接入应用已经创建。请立即保存只显示一次的密钥。", "success")
            return redirect(url_for("admin.client_detail", client_id=item.id))
    return render_template("admin/client_form.html", form=form, client=None)


@admin_bp.route("/clients/<int:client_id>/", methods=["GET", "POST"])
@admin_required
def client_detail(client_id: int):
    item = db.get_or_404(GatewayClient, client_id)
    form = ClientForm(obj=item)
    if request.method == "GET":
        form.redirect_uris.data = "\n".join(item.redirect_uris)
        scopes = set(item.scopes.split())
        form.allow_profile.data = "profile" in scopes
        form.allow_email.data = "email" in scopes
        form.allow_avatar.data = "avatar" in scopes
    if form.validate_on_submit():
        try:
            item.redirect_uris = _clean_redirect_uris(form.redirect_uris.data)
        except ValueError as error:
            form.redirect_uris.errors.append(str(error))
        else:
            item.name = form.name.data.strip()
            item.description = form.description.data.strip()
            item.homepage_url = form.homepage_url.data.strip()
            item.privacy_policy_url = form.privacy_policy_url.data.strip()
            item.service_terms_url = form.service_terms_url.data.strip()
            item.icon_url = form.icon_url.data.strip()
            item.scopes = _client_scopes(form)
            was_active = item.is_active
            item.is_active = bool(form.is_active.data)
            if was_active and not item.is_active:
                revoke_client_access(item.client_id)
            record_audit("admin.client.update", "client", item.client_id, item.name)
            db.session.commit()
            flash("应用设置已经保存。", "success")
            return redirect(url_for("admin.client_detail", client_id=item.id))
    secret = session.pop("new_client_secret", None)
    return render_template("admin/client_form.html", form=form, client=item, new_secret=secret)


@admin_bp.post("/clients/<int:client_id>/rotate-secret/")
@admin_required
def rotate_secret(client_id: int):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    item = db.get_or_404(GatewayClient, client_id)
    raw = new_token(32)
    item.set_secret(raw)
    revoke_client_access(item.client_id)
    record_audit("admin.client.rotate", "client", item.client_id, item.name)
    db.session.commit()
    session["new_client_secret"] = raw
    flash("应用密钥已轮换，旧密钥立即失效。", "success")
    return redirect(url_for("admin.client_detail", client_id=item.id))


@admin_bp.get("/mail/providers/")
@admin_required
def mail_providers():
    items = db.session.scalars(
        db.select(MailProvider).order_by(
            MailProvider.is_default.desc(),
            MailProvider.created_at.asc(),
        )
    ).all()
    return render_template(
        "admin/mail_providers.html",
        providers=items,
        empty_form=EmptyForm(),
    )


def _validate_mail_provider_form(form: MailProviderForm, item: MailProvider | None) -> bool:
    name = form.name.data.strip()
    duplicate = db.session.scalar(
        db.select(MailProvider).where(db.func.lower(MailProvider.name) == name.lower())
    )
    if duplicate is not None and (item is None or duplicate.id != item.id):
        form.name.errors.append("已经存在同名的邮件连接。")
    if form.password.data and form.clear_password.data:
        form.password.errors.append("新密码和清除密码不能同时选择。")
    if form.is_default.data and not form.is_active.data:
        form.is_default.errors.append("默认发送连接必须保持启用。")
    if form.security_mode.data == "plain" and not is_loopback_smtp_host(form.host.data):
        form.security_mode.errors.append("无加密SMTP只允许填写本机地址。")
    return not form.errors


def _apply_mail_provider_form(item: MailProvider, form: MailProviderForm) -> bool:
    previous = (
        item.host,
        item.port,
        item.security_mode,
        item.username,
        item.sender_email,
        item.sender_name,
        item.reply_to,
        item.timeout_seconds,
    )
    item.name = form.name.data.strip()
    item.host = form.host.data.strip().lower()
    item.port = form.port.data
    item.security_mode = form.security_mode.data
    item.username = form.username.data.strip()
    item.sender_email = form.sender_email.data.strip().lower()
    item.sender_name = form.sender_name.data.strip()
    item.reply_to = form.reply_to.data.strip().lower()
    item.timeout_seconds = form.timeout_seconds.data
    item.is_active = bool(form.is_active.data)
    password_changed = False
    if form.password.data:
        item.set_password(form.password.data)
        password_changed = True
    elif form.clear_password.data:
        item.password_ciphertext = ""
        password_changed = True
    current = (
        item.host,
        item.port,
        item.security_mode,
        item.username,
        item.sender_email,
        item.sender_name,
        item.reply_to,
        item.timeout_seconds,
    )
    if previous != current or password_changed:
        item.last_tested_at = None
        item.last_test_succeeded = None
        item.last_test_error = ""
    return password_changed


@admin_bp.route("/mail/providers/new/", methods=["GET", "POST"])
@admin_required
def mail_provider_new():
    form = MailProviderForm()
    if form.validate_on_submit() and _validate_mail_provider_form(form, None):
        item = MailProvider(
            name="",
            host="",
            port=587,
            security_mode="starttls",
            sender_email="",
            sender_name="baka网关",
        )
        _apply_mail_provider_form(item, form)
        db.session.add(item)
        db.session.flush()
        if form.is_default.data:
            set_default_mail_provider(item)
        else:
            ensure_default_mail_provider()
        record_audit("admin.mail_provider.create", "mail_provider", str(item.id), item.name)
        db.session.commit()
        flash("邮件连接已经保存，可以继续测试连接。", "success")
        return redirect(url_for("admin.mail_provider_detail", provider_id=item.id))
    return render_template(
        "admin/mail_provider_form.html",
        form=form,
        provider=None,
        test_form=MailTestForm(),
        empty_form=EmptyForm(),
    )


@admin_bp.route("/mail/providers/<int:provider_id>/", methods=["GET", "POST"])
@admin_required
def mail_provider_detail(provider_id: int):
    item = db.get_or_404(MailProvider, provider_id)
    form = MailProviderForm(obj=item)
    if form.validate_on_submit() and _validate_mail_provider_form(form, item):
        was_default = item.is_default
        password_changed = _apply_mail_provider_form(item, form)
        item.is_default = bool(form.is_default.data)
        if item.is_default:
            set_default_mail_provider(item)
        elif was_default:
            ensure_default_mail_provider()
        record_audit(
            "admin.mail_provider.update",
            "mail_provider",
            str(item.id),
            f"name={item.name};active={item.is_active};password_changed={password_changed}",
        )
        db.session.commit()
        flash("邮件连接设置已经保存。", "success")
        return redirect(url_for("admin.mail_provider_detail", provider_id=item.id))
    return render_template(
        "admin/mail_provider_form.html",
        form=form,
        provider=item,
        test_form=MailTestForm(),
        empty_form=EmptyForm(),
    )


def _record_provider_test(item: MailProvider, succeeded: bool, error_code: str = "") -> None:
    item.last_tested_at = datetime.now(UTC)
    item.last_test_succeeded = succeeded
    item.last_test_error = error_code[:240]


def _masked_email(value: str | None) -> str:
    if not value or "@" not in value:
        return "尚未填写邮箱"
    local, domain = value.rsplit("@", 1)
    if len(local) <= 2:
        hidden_local = local[:1] + "*"
    else:
        hidden_local = local[:1] + "*" * min(6, len(local) - 2) + local[-1:]
    return f"{hidden_local}@{domain}"


def _latest_admin_email_challenge(user: User) -> EmailChallenge | None:
    if not user.email:
        return None
    return db.session.scalar(
        db.select(EmailChallenge)
        .where(
            EmailChallenge.user_id == user.id,
            EmailChallenge.purpose == "verify_email",
            EmailChallenge.recipient_digest == recipient_digest(user.email),
            EmailChallenge.consumed_at.is_(None),
            EmailChallenge.invalidated_at.is_(None),
        )
        .order_by(EmailChallenge.created_at.desc())
        .limit(1)
    )


def _mail_policy_context(
    form: EmailPolicyForm,
    verification_form: AdminEmailVerificationForm | None = None,
) -> dict:
    policy = load_email_policy()
    readiness = email_policy_readiness(current_user)
    challenge = _latest_admin_email_challenge(current_user)
    now = datetime.now(UTC)
    resend_remaining = 0
    expires_remaining = 0
    if challenge is not None:
        resend_at = aware(challenge.created_at)
        expires_at = aware(challenge.expires_at)
        if resend_at is not None:
            resend_remaining = max(
                0,
                int((resend_at.timestamp() + policy.resend_seconds - now.timestamp()) + 0.999),
            )
        if expires_at is not None:
            expires_remaining = max(0, int(expires_at.timestamp() - now.timestamp()))
    return {
        "form": form,
        "verification_form": verification_form or AdminEmailVerificationForm(),
        "empty_form": EmptyForm(),
        "policy": policy,
        "readiness": readiness,
        "masked_email": _masked_email(current_user.email),
        "challenge": challenge,
        "resend_remaining": resend_remaining,
        "expires_remaining": expires_remaining,
    }


@admin_bp.route("/mail/policy/", methods=["GET", "POST"])
@admin_required
def mail_policy():
    policy = load_email_policy()
    form = EmailPolicyForm()
    if request.method == "GET":
        form.registration_enabled.data = policy.registration_enabled
        form.profile_verification_enabled.data = policy.profile_verification_enabled
        form.password_reset_enabled.data = policy.password_reset_enabled
        form.code_ttl_minutes.data = policy.code_ttl_minutes
        form.resend_seconds.data = policy.resend_seconds
        form.max_attempts.data = policy.max_attempts
    if form.validate_on_submit():
        candidate = EmailFeaturePolicy(
            registration_enabled=bool(form.registration_enabled.data),
            profile_verification_enabled=bool(form.profile_verification_enabled.data),
            password_reset_enabled=bool(form.password_reset_enabled.data),
            code_ttl_minutes=form.code_ttl_minutes.data,
            resend_seconds=form.resend_seconds.data,
            max_attempts=form.max_attempts.data,
        )
        wants_public_feature = any(
            (
                candidate.registration_enabled,
                candidate.profile_verification_enabled,
                candidate.password_reset_enabled,
            )
        )
        readiness = email_policy_readiness(current_user)
        if wants_public_feature and not readiness["current_administrator_verified"]:
            form.registration_enabled.errors.append(
                "当前管理员必须先通过邮箱验证码，才能开启公开邮件功能。"
            )
        elif wants_public_feature and not readiness["provider_tested"]:
            form.registration_enabled.errors.append(
                "默认邮件连接必须先完成一次成功测试或验证码投递。"
            )
        else:
            save_email_policy(candidate)
            record_audit(
                "admin.email_policy.update",
                "email_policy",
                "global",
                (
                    f"registration={candidate.registration_enabled};"
                    f"profile={candidate.profile_verification_enabled};"
                    f"password_reset={candidate.password_reset_enabled};"
                    f"ttl={candidate.code_ttl_minutes};"
                    f"resend={candidate.resend_seconds};"
                    f"attempts={candidate.max_attempts}"
                ),
            )
            db.session.commit()
            flash("邮箱验证策略已经保存。", "success")
            return redirect(url_for("admin.mail_policy"))
    return render_template("admin/mail_policy.html", **_mail_policy_context(form))


@admin_bp.post("/mail/policy/send-code/")
@admin_required
def mail_policy_send_code():
    if not EmptyForm().validate_on_submit():
        abort(400)
    if current_user.email_verified:
        flash("当前管理员邮箱已经完成验证。", "info")
        return redirect(url_for("admin.mail_policy"))
    if not current_user.email:
        flash("请先在个人资料中填写管理员邮箱。", "error")
        return redirect(url_for("admin.mail_policy"))
    policy = load_email_policy()
    readiness = email_policy_readiness(current_user)
    provider = readiness["provider"]
    if provider is None:
        flash("请先添加并启用一条默认邮件连接。", "error")
        return redirect(url_for("admin.mail_policy"))
    try:
        _challenge, code = issue_email_challenge(
            "verify_email",
            current_user.email,
            user_id=current_user.id,
            request_fingerprint=request_fingerprint("admin-email-verification"),
            policy=policy.challenge_policy(),
        )
        send_verification_code(
            provider,
            current_user.email,
            code,
            ttl_minutes=policy.code_ttl_minutes,
        )
    except ChallengeRateLimited as error:
        db.session.rollback()
        flash(f"发送过于频繁，请在 {error.retry_after} 秒后再试。", "error")
    except MailDeliveryError as error:
        db.session.rollback()
        record_audit(
            "admin.email_verification.send",
            "user",
            str(current_user.id),
            f"result=failed;code={error.code}",
        )
        db.session.commit()
        flash(error.public_message, "error")
    else:
        _record_provider_test(provider, True)
        record_audit(
            "admin.email_verification.send",
            "user",
            str(current_user.id),
            "result=success",
        )
        db.session.commit()
        flash("验证码已经发送到管理员邮箱。", "success")
    return redirect(url_for("admin.mail_policy"))


@admin_bp.post("/mail/policy/verify-code/")
@admin_required
def mail_policy_verify_code():
    form = AdminEmailVerificationForm()
    if current_user.email_verified:
        flash("当前管理员邮箱已经完成验证。", "info")
        return redirect(url_for("admin.mail_policy"))
    challenge = _latest_admin_email_challenge(current_user)
    if not form.validate_on_submit() or challenge is None:
        flash(
            form.code.errors[0] if form.code.errors else "请先发送新的邮箱验证码。",
            "error",
        )
        return redirect(url_for("admin.mail_policy"))
    result = consume_email_challenge(
        challenge.public_id,
        "verify_email",
        form.code.data,
    )
    if result.verified:
        current_user.email_verified = True
        record_audit(
            "admin.email_verification.complete",
            "user",
            str(current_user.id),
            "result=success",
        )
        db.session.commit()
        flash("管理员邮箱验证完成，邮件策略已经解锁。", "success")
    else:
        db.session.commit()
        messages = {
            "expired": "验证码已经过期，请重新发送。",
            "locked": "验证码已失效或尝试次数已用完，请重新发送。",
            "consumed": "验证码已经使用，请重新发送。",
            "invalid": "验证码不正确，请检查后重试。",
        }
        flash(messages.get(result.status, "验证码无法使用，请重新发送。"), "error")
    return redirect(url_for("admin.mail_policy"))


@admin_bp.get("/mail/templates/")
@admin_required
def mail_templates():
    added = ensure_default_mail_templates()
    upgraded = upgrade_legacy_mail_templates()
    if added or upgraded:
        db.session.commit()
    items = list_mail_templates()
    cards = [
        {
            "item": item,
            "definition": template_definition(item.key),
            "variables": template_variables(item.key),
            "custom": template_is_custom(item),
        }
        for item in items
    ]
    return render_template("admin/mail_templates.html", templates=cards)


@admin_bp.route("/mail/templates/<int:template_id>/", methods=["GET", "POST"])
@admin_required
def mail_template_detail(template_id: int):
    item = db.get_or_404(MailTemplate, template_id)
    definition = template_definition(item.key)
    form = MailTemplateForm()
    if request.method == "GET":
        form.template_key.data = item.key
        form.subject.data = item.subject
        form.body_html.data = item.body_html
    if form.validate_on_submit():
        if form.template_key.data != item.key:
            abort(400)
        item.name = definition.name
        item.subject = form.subject.data
        item.body_html = form.body_html.data
        record_audit(
            "admin.mail_template.update",
            "mail_template",
            str(item.id),
            f"key={item.key};result=success",
        )
        db.session.commit()
        flash("邮件模板已经保存。", "success")
        return redirect(url_for("admin.mail_template_detail", template_id=item.id))
    return render_template(
        "admin/mail_template_detail.html",
        form=form,
        item=item,
        definition=definition,
        variables=template_variables(item.key),
        sample_variables=sample_template_variables(item.key),
        custom=template_is_custom(item),
        empty_form=EmptyForm(),
    )


@admin_bp.post("/mail/templates/<int:template_id>/reset/")
@admin_required
def mail_template_reset(template_id: int):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    item = db.get_or_404(MailTemplate, template_id)
    reset_mail_template(item)
    record_audit(
        "admin.mail_template.reset",
        "mail_template",
        str(item.id),
        f"key={item.key};result=success",
    )
    db.session.commit()
    flash("邮件模板已经恢复默认内容。", "success")
    return redirect(url_for("admin.mail_template_detail", template_id=item.id))


@admin_bp.post("/mail/providers/<int:provider_id>/test-connection/")
@admin_required
def mail_provider_test_connection(provider_id: int):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    item = db.get_or_404(MailProvider, provider_id)
    try:
        test_mail_provider_connection(item)
    except MailDeliveryError as error:
        _record_provider_test(item, False, error.code)
        record_audit(
            "admin.mail_provider.test",
            "mail_provider",
            str(item.id),
            f"result=failed;code={error.code}",
        )
        db.session.commit()
        flash(error.public_message, "error")
    else:
        _record_provider_test(item, True)
        record_audit(
            "admin.mail_provider.test",
            "mail_provider",
            str(item.id),
            "result=success",
        )
        db.session.commit()
        flash("SMTP连接与身份验证测试通过。", "success")
    return redirect(url_for("admin.mail_provider_detail", provider_id=item.id))


@admin_bp.post("/mail/providers/<int:provider_id>/test-email/")
@admin_required
def mail_provider_test_email(provider_id: int):
    item = db.get_or_404(MailProvider, provider_id)
    form = MailTestForm()
    if not form.validate_on_submit():
        edit_form = MailProviderForm(obj=item)
        return (
            render_template(
                "admin/mail_provider_form.html",
                form=edit_form,
                provider=item,
                test_form=form,
                empty_form=EmptyForm(),
            ),
            400,
        )
    try:
        send_mail_provider_test(item, form.recipient.data.strip().lower())
    except MailDeliveryError as error:
        _record_provider_test(item, False, error.code)
        record_audit(
            "admin.mail_provider.test_email",
            "mail_provider",
            str(item.id),
            f"result=failed;code={error.code}",
        )
        db.session.commit()
        flash(error.public_message, "error")
    else:
        _record_provider_test(item, True)
        record_audit(
            "admin.mail_provider.test_email",
            "mail_provider",
            str(item.id),
            "result=success",
        )
        db.session.commit()
        flash("测试邮件已经交给邮件服务器发送。", "success")
    return redirect(url_for("admin.mail_provider_detail", provider_id=item.id))


@admin_bp.post("/mail/providers/<int:provider_id>/default/")
@admin_required
def mail_provider_default(provider_id: int):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    item = db.get_or_404(MailProvider, provider_id)
    if not item.is_active:
        flash("请先启用这条邮件连接，再设为默认。", "error")
    else:
        set_default_mail_provider(item)
        record_audit("admin.mail_provider.default", "mail_provider", str(item.id), item.name)
        db.session.commit()
        flash("默认邮件连接已经更新。", "success")
    return redirect(url_for("admin.mail_providers"))


@admin_bp.post("/mail/providers/<int:provider_id>/delete/")
@admin_required
def mail_provider_delete(provider_id: int):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    item = db.get_or_404(MailProvider, provider_id)
    target_id = str(item.id)
    target_name = item.name
    db.session.delete(item)
    db.session.flush()
    ensure_default_mail_provider()
    record_audit("admin.mail_provider.delete", "mail_provider", target_id, target_name)
    db.session.commit()
    flash("邮件连接已经删除。", "success")
    return redirect(url_for("admin.mail_providers"))


@admin_bp.get("/logs/")
@admin_required
def logs():
    login_items = db.session.scalars(
        db.select(LoginLog).order_by(LoginLog.created_at.desc()).limit(100)
    ).all()
    audit_items = db.session.scalars(
        db.select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100)
    ).all()
    return render_template("admin/logs.html", login_items=login_items, audit_items=audit_items)


@admin_bp.route("/site/footer/", methods=["GET", "POST"])
@admin_required
def footer_settings():
    footer = load_footer_content()
    if request.method == "POST":
        if not EmptyForm().validate_on_submit():
            abort(400)
        try:
            columns = json.loads(request.form.get("footer_columns", "[]"))
        except (TypeError, ValueError):
            columns = []
        if not isinstance(columns, list):
            columns = []
        footer = {
            "description": request.form.get("description", "").strip()[:300],
            "copyright": request.form.get("copyright", "").strip()[:255],
            "columns": columns[:8],
        }
        save_footer_content(footer)
        record_audit("site.footer.update", "site", "footer", "更新全站页尾内容")
        db.session.commit()
        flash("全站页尾信息已经保存。", "success")
        return redirect(url_for("admin.footer_settings"))
    return render_template("admin/footer_settings.html", footer=footer)


@admin_bp.route("/appearance/font/", methods=["GET", "POST"])
@admin_required
def theme_font():
    form = InterfaceAppearanceForm()
    form.font_style.choices = list(GLOBAL_FONT_CHOICES)
    if request.method == "GET":
        current = load_theme_settings()["global_font_style"]
        form.font_style.data = str(current)
    if form.validate_on_submit():
        if form.font_style.data not in GLOBAL_FONT_VALUES:
            abort(400)
        set_setting("global_font_style", form.font_style.data)
        record_audit(
            "site.interface.update",
            "site",
            "font",
            f"全站字体：{form.font_style.data}",
        )
        db.session.commit()
        flash("全站字体已经更新。", "success")
        return redirect(url_for("admin.theme_font"))
    return render_template(
        "admin/theme_font.html",
        form=form,
        font_choices=GLOBAL_FONT_CHOICES,
    )


@admin_bp.route("/appearance/hints/", methods=["GET", "POST"])
@admin_required
def theme_hints():
    form = EmptyForm()
    settings = load_theme_settings()
    if form.validate_on_submit():
        visible = bool(settings["admin_menu_subtitles_visible"])
        set_setting("admin_menu_subtitles_visible", "false" if visible else "true")
        record_audit(
            "site.interface.menu_subtitles",
            "site",
            "hints",
            "hidden" if visible else "visible",
        )
        db.session.commit()
        flash(
            "后台菜单小标题已关闭。" if visible else "后台菜单小标题已显示。",
            "success",
        )
        return redirect(url_for("admin.theme_hints"))
    return render_template(
        "admin/theme_hints.html",
        form=form,
        subtitles_visible=bool(settings["admin_menu_subtitles_visible"]),
    )


@admin_bp.route("/appearance/transitions/", methods=["GET", "POST"])
@admin_required
def theme_transitions():
    form = TransitionSettingsForm()
    form.transition_style.choices = list(PAGE_TRANSITION_CHOICES)
    settings = load_theme_settings()
    if request.method == "GET":
        form.transition_style.data = str(settings["page_transition_style"])
        form.transition_duration.data = int(settings["page_transition_duration"])
        form.transition_color_start.data = str(settings["page_transition_color_start"])
        form.transition_color_middle.data = str(settings["page_transition_color_middle"])
        form.transition_color_end.data = str(settings["page_transition_color_end"])
    if form.validate_on_submit():
        if form.transition_style.data not in PAGE_TRANSITION_VALUES:
            abort(400)
        duration = max(300, min(2400, int(form.transition_duration.data)))
        set_setting("page_transition_style", form.transition_style.data)
        set_setting("page_transition_duration", str(duration))
        for name in (
            "transition_color_start",
            "transition_color_middle",
            "transition_color_end",
        ):
            set_setting(f"page_{name}", getattr(form, name).data.lower())
        record_audit(
            "site.transition.update",
            "site",
            "transitions",
            f"{form.transition_style.data} / {duration}ms",
        )
        db.session.commit()
        flash("全站页面过渡已经更新。", "success")
        return redirect(url_for("admin.theme_transitions"))
    return render_template(
        "admin/theme_transitions.html",
        form=form,
        transition_choices=PAGE_TRANSITION_CHOICES,
    )


@admin_bp.route("/appearance/dialogs/", methods=["GET", "POST"])
@admin_required
def theme_dialogs():
    form = DialogAppearanceForm()
    form.dialog_style.choices = list(DIALOG_STYLE_CHOICES)
    form.dialog_shadow.choices = list(DIALOG_SHADOW_CHOICES)
    settings = load_theme_settings()
    if request.method == "GET":
        for name in (
            "dialog_style",
            "dialog_color_start",
            "dialog_color_end",
            "dialog_accent",
            "dialog_radius",
            "dialog_width",
            "dialog_backdrop_blur",
            "dialog_shadow",
        ):
            getattr(form, name).data = settings[name]
    if form.validate_on_submit():
        if form.dialog_style.data not in DIALOG_STYLE_VALUES:
            abort(400)
        if form.dialog_shadow.data not in DIALOG_SHADOW_VALUES:
            abort(400)
        set_setting("dialog_style", form.dialog_style.data)
        set_setting("dialog_shadow", form.dialog_shadow.data)
        for name in ("dialog_color_start", "dialog_color_end", "dialog_accent"):
            set_setting(name, getattr(form, name).data.lower())
        for name in ("dialog_radius", "dialog_width", "dialog_backdrop_blur"):
            set_setting(name, str(getattr(form, name).data))
        record_audit(
            "site.dialog.update",
            "site",
            "dialogs",
            f"{form.dialog_style.data} / {form.dialog_width.data}px",
        )
        db.session.commit()
        flash("全站弹窗外观已经更新。", "success")
        return redirect(url_for("admin.theme_dialogs"))
    return render_template(
        "admin/theme_dialogs.html",
        form=form,
        dialog_style_choices=DIALOG_STYLE_CHOICES,
        dialog_shadow_choices=DIALOG_SHADOW_CHOICES,
    )
