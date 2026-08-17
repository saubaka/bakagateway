from __future__ import annotations

import io
import ipaddress
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import qrcode
from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from flask_login import current_user, login_required, logout_user
from qrcode.image.pure import PyPNGImage
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash

from app.blueprints.auth import auth_bp
from app.extensions import db
from app.forms import (
    ChangeEmailRequestForm,
    EmailVerificationForm,
    EmptyForm,
    FirstAdministratorForm,
    ForgotPasswordForm,
    LoginForm,
    PasswordResetConfirmForm,
    ProfileForm,
    RegisterForm,
    TwoFactorForm,
)
from app.models import (
    EmailChallenge,
    GatewayClient,
    PendingEmailChange,
    PendingRegistration,
    Role,
    User,
)
from app.security import (
    generate_totp_secret,
    is_safe_local_url,
    new_token,
    request_fingerprint,
    verify_totp,
)
from app.services.auth import (
    administrator_exists,
    aware,
    current_gateway_session,
    establish_session,
    recent_login_failures,
    record_audit,
    record_login,
    revoke_session,
    seed_roles,
)
from app.services.email_policy import (
    default_mail_provider,
    effective_email_features,
    load_email_policy,
)
from app.services.email_security import (
    ChallengeRateLimited,
    consume_email_challenge,
    issue_email_challenge,
    recipient_digest,
)
from app.services.local_recovery import (
    claim_local_recovery_token,
    request_is_loopback,
)
from app.services.mail_delivery import MailDeliveryError, send_verification_code

DUMMY_PASSWORD_HASH = (
    "scrypt:32768:8:1$9rQvHjH4W4hFhaDR$"
    "ea91623166f3ac5dbdd29872f45c956df1675e4f8fd1ce3efb4c03588df9ad5f"
    "6279904ca87016f9a7598d3f60b26b5f8b155354c49b52e65d801226878c2063"
)
AVATAR_MAX_BYTES = 2 * 1024 * 1024
PENDING_REGISTRATION_SESSION_KEY = "pending_registration"
PENDING_REGISTRATION_TTL = timedelta(minutes=30)
PENDING_EMAIL_CHANGE_SESSION_KEY = "pending_email_change"


def _pending_email_change() -> PendingEmailChange | None:
    public_id = session.get(PENDING_EMAIL_CHANGE_SESSION_KEY)
    if not isinstance(public_id, str) or not public_id:
        return None
    pending = db.session.scalar(
        db.select(PendingEmailChange).where(
            PendingEmailChange.public_id == public_id,
            PendingEmailChange.consumed_at.is_(None),
            PendingEmailChange.invalidated_at.is_(None),
        )
    )
    if pending is None or aware(pending.expires_at) <= datetime.now(UTC):
        session.pop(PENDING_EMAIL_CHANGE_SESSION_KEY, None)
        return None
    return pending


DUMMY_PASSWORD_HASH = (
    "scrypt:32768:8:1$9rQvHjH4W4hFhaDR$"
    "ea91623166f3ac5dbdd29872f45c956df1675e4f8fd1ce3efb4c03588df9ad5f"
    "6279904ca87016f9a7598d3f60b26b5f8b155354c49b52e65d801226878c2063"
)
AVATAR_MAX_BYTES = 2 * 1024 * 1024
PENDING_REGISTRATION_SESSION_KEY = "pending_registration"
PENDING_REGISTRATION_TTL = timedelta(minutes=30)


def _find_user(identifier: str) -> User | None:
    normalized = identifier.strip().lower()
    return db.session.scalar(
        db.select(User).where(or_(User.username == normalized, User.email == normalized))
    )


def _bootstrap_request_is_local() -> bool:
    addresses = [request.remote_addr or ""]
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        addresses.extend(part.strip() for part in forwarded.split(","))
    try:
        return bool(addresses) and all(
            ipaddress.ip_address(address).is_loopback for address in addresses if address
        )
    except ValueError:
        return False


def _next_target() -> str:
    value = request.args.get("next") or session.pop("login_next", None)
    return value if is_safe_local_url(value) else url_for("portal.dashboard")


def _finish_login(user: User, remember: bool) -> str:
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(UTC)
    establish_session(user, remember)
    record_login(user.username, user, True, "success")
    db.session.commit()
    flash(f"欢迎回来，{user.display_name}。", "success")
    return _next_target()


def _remember_next(value: str | None) -> None:
    if is_safe_local_url(value):
        session["login_next"] = value


def _oauth_client_for_login() -> GatewayClient | None:
    target = request.args.get("next") or session.get("login_next")
    if not is_safe_local_url(target):
        return None
    parts = urlsplit(target)
    if parts.path.rstrip("/") != "/oauth/authorize":
        return None
    client_id = parse_qs(parts.query).get("client_id", [""])[0]
    if not client_id:
        return None
    return db.session.scalar(
        db.select(GatewayClient).where(
            GatewayClient.client_id == client_id,
            GatewayClient.is_active.is_(True),
        )
    )


def _registration_enabled() -> bool:
    return effective_email_features()["registration"]


def _masked_email(value: str | None) -> str:
    if not value or "@" not in value:
        return "未填写邮箱"
    local, domain = value.split("@", 1)
    visible = local[:1] if local else ""
    return f"{visible}{'*' * max(4, min(8, len(local) - 1))}@{domain}"


def _latest_email_challenge(
    purpose: str,
    recipient: str,
    *,
    user_id: int | None = None,
    pending_registration_id: int | None = None,
) -> EmailChallenge | None:
    query = db.select(EmailChallenge).where(
        EmailChallenge.purpose == purpose,
        EmailChallenge.recipient_digest == recipient_digest(recipient),
        EmailChallenge.consumed_at.is_(None),
        EmailChallenge.invalidated_at.is_(None),
    )
    if user_id is not None:
        query = query.where(EmailChallenge.user_id == user_id)
    if pending_registration_id is not None:
        query = query.where(
            EmailChallenge.pending_registration_id == pending_registration_id
        )
    return db.session.scalar(
        query.order_by(EmailChallenge.created_at.desc()).limit(1)
    )


def _pending_registration() -> PendingRegistration | None:
    public_id = session.get(PENDING_REGISTRATION_SESSION_KEY)
    if not isinstance(public_id, str) or not public_id:
        return None
    pending = db.session.scalar(
        db.select(PendingRegistration).where(
            PendingRegistration.public_id == public_id,
            PendingRegistration.completed_at.is_(None),
        )
    )
    if pending is None or aware(pending.expires_at) <= datetime.now(UTC):
        session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
        return None
    return pending


def _verification_timing(
    challenge: EmailChallenge | None,
) -> tuple[int, int]:
    if challenge is None:
        return 0, 0
    policy = load_email_policy()
    now = datetime.now(UTC)
    created_at = aware(challenge.created_at)
    expires_at = aware(challenge.expires_at)
    resend_remaining = (
        max(
            0,
            int(
                created_at.timestamp()
                + policy.resend_seconds
                - now.timestamp()
                + 0.999
            ),
        )
        if created_at is not None
        else 0
    )
    expires_remaining = (
        max(0, int(expires_at.timestamp() - now.timestamp()))
        if expires_at is not None
        else 0
    )
    return resend_remaining, expires_remaining


def _email_template_key(purpose: str, verification_kind: str) -> str:
    if purpose == "register":
        return "registration"
    if purpose == "verify_email":
        return (
            "admin_email_verification"
            if verification_kind == "administrator"
            else "account_email_verification"
        )
    if purpose == "change_email":
        return "change_email"
    if purpose == "password_reset":
        return "password_reset"
    return "account_email_verification"


def _deliver_email_challenge(
    purpose: str,
    recipient: str,
    verification_kind: str,
    *,
    user_id: int | None = None,
    pending_registration_id: int | None = None,
    fingerprint_scope: str,
) -> EmailChallenge:
    provider = default_mail_provider()
    if provider is None:
        raise MailDeliveryError("not_configured", "邮件验证暂时不可用，请稍后再试。")
    policy = load_email_policy()
    challenge, code = issue_email_challenge(
        purpose,
        recipient,
        user_id=user_id,
        pending_registration_id=pending_registration_id,
        request_fingerprint=request_fingerprint(fingerprint_scope),
        policy=policy.challenge_policy(),
    )
    send_verification_code(
        provider,
        recipient,
        code,
        ttl_minutes=policy.code_ttl_minutes,
        verification_kind=verification_kind,
        template_key=_email_template_key(purpose, verification_kind),
    )
    provider.last_tested_at = datetime.now(UTC)
    provider.last_test_succeeded = True
    provider.last_test_error = ""
    return challenge


def _render_email_verification(
    *,
    verification_mode: str,
    recipient: str,
    challenge: EmailChallenge | None,
    form: EmailVerificationForm | None = None,
    resend_form: EmptyForm | None = None,
    resend_url: str | None = None,
    back_url: str | None = None,
):
    resend_remaining, expires_remaining = _verification_timing(challenge)
    registration_mode = verification_mode == "registration"
    change_mode = verification_mode == "change_email"
    if resend_url is None:
        if registration_mode:
            resend_url = url_for("auth.registration_email_resend")
        elif change_mode:
            resend_url = url_for("auth.change_email_resend")
        else:
            resend_url = url_for("auth.request_email_verification")
    if back_url is None:
        if registration_mode:
            back_url = url_for("auth.register")
        elif change_mode:
            back_url = url_for("portal.security")
        else:
            back_url = url_for("portal.profile")
    return render_template(
        "auth/email_verification.html",
        verification_mode=verification_mode,
        masked_email=_masked_email(recipient),
        policy=load_email_policy(),
        challenge=challenge,
        resend_remaining=resend_remaining,
        expires_remaining=expires_remaining,
        form=form or EmailVerificationForm(),
        resend_form=resend_form or EmptyForm(),
        resend_url=resend_url,
        back_url=back_url,
        auth_centered=True,
    )


def _avatar_directory() -> Path:
    target = Path(current_app.instance_path) / "uploads" / "avatars"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _avatar_extension(payload: bytes) -> str | None:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if payload.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return ".webp"
    return None


def _delete_avatar(filename: str | None) -> None:
    if not filename:
        return
    safe_name = Path(filename).name
    if safe_name != filename:
        return
    (_avatar_directory() / safe_name).unlink(missing_ok=True)


@auth_bp.route("/setup/administrator/", methods=["GET", "POST"])
def setup_administrator():
    if administrator_exists():
        target = "portal.dashboard" if current_user.is_authenticated else "auth.login"
        return redirect(url_for(target))
    if not _bootstrap_request_is_local():
        abort(403)

    _remember_next(request.args.get("next"))
    form = FirstAdministratorForm()
    password_mismatch = False
    if form.validate_on_submit():
        username = form.username.data.strip().lower()
        email = form.email.data.strip().lower()
        existing_user = db.session.scalar(
            db.select(User).where(User.username == username)
        )
        email_owner = db.session.scalar(db.select(User).where(User.email == email))
        if email_owner is not None and email_owner is not existing_user:
            form.email.errors.append("这个邮箱已经被使用。")
        if not form.email.errors:
            _member, administrator = seed_roles()
            if administrator_exists():
                db.session.rollback()
                flash("首位管理员已经由另一个请求完成创建，请直接登录。", "info")
                return redirect(url_for("auth.login"))
            if existing_user is None:
                # The database invariant forbids an active ordinary user when no
                # active administrator exists. Create the bootstrap account
                # inactive, attach its administrator role, then activate it.
                user = User(
                    username=username,
                    email=email,
                    display_name=form.display_name.data.strip(),
                    email_verified=False,
                    status="inactive",
                    roles=[administrator],
                )
                db.session.add(user)
            else:
                # Older databases could contain members after an administrator
                # was manually removed. This route is loopback-only, so it may
                # safely reclaim the selected identity instead of rejecting the
                # ID and leaving the gateway permanently without an owner.
                user = existing_user
                user.email = email
                user.display_name = form.display_name.data.strip()
                user.email_verified = False
                user.roles = [administrator]
            user.set_password(form.password.data)
            db.session.flush()
            user.status = "active"
            db.session.flush()
            target = _next_target()
            establish_session(user, False)
            record_login(user.username, user, True, "bootstrap_administrator")
            record_audit(
                "administrator.bootstrap",
                "user",
                str(user.id),
                "首次启动向导创建或接管首位管理员",
            )
            db.session.commit()
            flash("首位管理员已经创建，baka网关可以正式使用了。", "success")
            return redirect(target)
    elif request.method == "POST":
        password_mismatch = bool(
            form.password.data
            and form.password_confirm.data
            and form.password.data != form.password_confirm.data
        )
        if password_mismatch:
            form.password_confirm.errors = [
                error
                for error in form.password_confirm.errors
                if error != "两次密码不一致。"
            ]
    return render_template(
        "auth/setup_administrator.html",
        form=form,
        password_mismatch=password_mismatch,
    )


@auth_bp.get("/recovery/local/<token>/")
def local_recovery(token: str):
    if not request_is_loopback() or not claim_local_recovery_token(token):
        abort(404)
    administrator = db.session.scalar(
        db.select(User)
        .join(User.roles)
        .where(Role.name == "administrator", User.status == "active")
        .limit(1)
    )
    if administrator is None:
        return redirect(url_for("auth.setup_administrator"))
    establish_session(administrator, False)
    record_login(
        administrator.username,
        administrator,
        True,
        "local_recovery",
    )
    record_audit(
        "administrator.local_recovery",
        "user",
        str(administrator.id),
        "本机一次性恢复入口建立临时管理员会话",
    )
    db.session.commit()
    flash("本机恢复会话已经建立，请及时检查管理员账号安全。", "info")
    return redirect(url_for("admin.dashboard"))


@auth_bp.route("/login/", methods=["GET", "POST"])
def login():
    if not administrator_exists():
        return redirect(
            url_for("auth.setup_administrator", next=request.args.get("next"))
        )
    if current_user.is_authenticated:
        return redirect(url_for("portal.dashboard"))
    form = LoginForm()
    _remember_next(request.args.get("next"))
    if form.validate_on_submit():
        identifier = form.identifier.data.strip().lower()
        if recent_login_failures(identifier) >= current_app.config["LOGIN_LIMIT"]:
            flash("尝试次数较多，请十五分钟后再试。", "error")
            return (
                render_template(
                    "auth/login.html",
                    form=form,
                    oauth_client=_oauth_client_for_login(),
                    auth_centered=True,
                    registration_enabled=_registration_enabled(),
                ),
                429,
            )
        user = _find_user(identifier)
        password_ok = (
            user.check_password(form.password.data)
            if user
            else check_password_hash(DUMMY_PASSWORD_HASH, form.password.data)
        )
        now = datetime.now(UTC)
        locked = bool(user and user.locked_until and aware(user.locked_until) > now)
        if (
            user
            and user.is_active
            and not locked
            and password_ok
        ):
            if user.totp_enabled:
                session["preauth_user_id"] = user.id
                session["preauth_remember"] = bool(form.remember.data)
                session["preauth_expires"] = int((now + timedelta(minutes=10)).timestamp())
                return redirect(url_for("auth.two_factor"))
            return redirect(_finish_login(user, bool(form.remember.data)))
        if user:
            user.failed_attempts += 1
            if user.failed_attempts >= current_app.config["LOGIN_LIMIT"]:
                user.locked_until = now + timedelta(minutes=15)
        record_login(identifier, user, False, "invalid_credentials")
        db.session.commit()
        flash("账号或密码不正确。", "error")
    return render_template(
        "auth/login.html",
        form=form,
        oauth_client=_oauth_client_for_login(),
        auth_centered=True,
        registration_enabled=_registration_enabled(),
    )


@auth_bp.get("/privacy/")
def privacy_policy():
    return render_template("auth/privacy_policy.html")


@auth_bp.get("/terms/")
def service_terms():
    return render_template("auth/service_terms.html")


@auth_bp.route("/two-factor/", methods=["GET", "POST"])
def two_factor():
    user_id = session.get("preauth_user_id")
    expires = session.get("preauth_expires", 0)
    user = db.session.get(User, user_id) if user_id else None
    if user is None or int(expires) < int(datetime.now(UTC).timestamp()):
        session.pop("preauth_user_id", None)
        flash("验证已经过期，请重新登录。", "info")
        return redirect(url_for("auth.login"))
    form = TwoFactorForm()
    if form.validate_on_submit():
        if user.totp_secret and verify_totp(user.totp_secret, form.code.data):
            remember = bool(session.pop("preauth_remember", False))
            session.pop("preauth_user_id", None)
            session.pop("preauth_expires", None)
            return redirect(_finish_login(user, remember))
        record_login(user.username, user, False, "invalid_totp")
        db.session.commit()
        flash("验证码不正确，请检查时间后重试。", "error")
    return render_template(
        "auth/two_factor.html",
        form=form,
        user=user,
        oauth_client=_oauth_client_for_login(),
        auth_centered=True,
    )


@auth_bp.route("/register/", methods=["GET", "POST"])
def register():
    if not administrator_exists():
        return redirect(
            url_for("auth.setup_administrator", next=request.args.get("next"))
        )
    if not _registration_enabled():
        abort(403)
    if current_user.is_authenticated:
        return redirect(url_for("portal.dashboard"))
    _remember_next(request.args.get("next"))
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data.strip().lower()
        email = form.email.data.strip().lower()
        if db.session.scalar(db.select(User).where(User.username == username)):
            form.username.errors.append("这个baka网关 ID 已经被使用。")
        if db.session.scalar(db.select(User).where(User.email == email)):
            form.email.errors.append("这个邮箱已经被其他账号使用。")
        if not form.username.errors and not form.email.errors:
            continuation = session.get("login_next")
            pending = PendingRegistration(
                public_id=new_token(24),
                username=username,
                display_name=form.display_name.data.strip(),
                expires_at=datetime.now(UTC) + PENDING_REGISTRATION_TTL,
            )
            pending.set_email(email)
            pending.set_password(form.password.data)
            pending.set_continuation(
                continuation if is_safe_local_url(continuation) else ""
            )
            db.session.add(pending)
            try:
                db.session.flush()
                _deliver_email_challenge(
                    "register",
                    email,
                    "registration",
                    pending_registration_id=pending.id,
                    fingerprint_scope="registration-email",
                )
            except ChallengeRateLimited as error:
                db.session.rollback()
                flash(f"发送过于频繁，请在 {error.retry_after} 秒后再试。", "error")
                return redirect(url_for("auth.register"))
            except MailDeliveryError as error:
                db.session.rollback()
                record_audit(
                    "account.register.email.send",
                    "pending_registration",
                    "new",
                    f"result=failed;code={error.code}",
                )
                db.session.commit()
                flash(error.public_message, "error")
                return redirect(url_for("auth.register"))
            record_audit(
                "account.register.email.send",
                "pending_registration",
                "new",
                "result=success",
            )
            db.session.commit()
            session[PENDING_REGISTRATION_SESSION_KEY] = pending.public_id
            flash("验证码已经发送，请完成邮箱验证。", "success")
            return redirect(url_for("auth.registration_email_verification"))
    return render_template(
        "auth/register.html",
        form=form,
        oauth_client=_oauth_client_for_login(),
        auth_centered=True,
    )


@auth_bp.route("/register/verify-email/", methods=["GET", "POST"])
def registration_email_verification():
    if not administrator_exists():
        return redirect(url_for("auth.setup_administrator"))
    if current_user.is_authenticated:
        return redirect(url_for("portal.dashboard"))
    if not _registration_enabled():
        flash("管理员暂时关闭了新账号邮箱验证。", "error")
        return redirect(url_for("auth.login"))
    pending = _pending_registration()
    if pending is None:
        flash("注册验证已经过期，请重新填写注册资料。", "info")
        return redirect(url_for("auth.register"))
    recipient = pending.get_email()
    challenge = _latest_email_challenge(
        "register",
        recipient,
        pending_registration_id=pending.id,
    )
    form = EmailVerificationForm()
    if form.validate_on_submit():
        if challenge is None:
            flash("请先重新发送邮箱验证码。", "error")
            return redirect(url_for("auth.registration_email_verification"))
        result = consume_email_challenge(
            challenge.public_id,
            "register",
            form.code.data,
        )
        if result.verified:
            duplicate_username = db.session.scalar(
                db.select(User.id).where(User.username == pending.username)
            )
            duplicate_email = db.session.scalar(
                db.select(User.id).where(User.email == recipient)
            )
            if duplicate_username or duplicate_email:
                db.session.rollback()
                session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
                flash("注册资料已经被其他账号使用，请重新填写。", "error")
                return redirect(url_for("auth.register"))
            member, _administrator = seed_roles()
            user = User(
                username=pending.username,
                email=recipient,
                display_name=pending.display_name,
                email_verified=True,
                roles=[member],
            )
            user.password_hash = pending.password_hash
            db.session.add(user)
            pending.completed_at = datetime.now(UTC)
            try:
                db.session.flush()
            except IntegrityError:
                db.session.rollback()
                session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
                flash("注册资料已经被其他账号使用，请重新填写。", "error")
                return redirect(url_for("auth.register"))
            continuation = pending.get_continuation()
            target = (
                continuation
                if is_safe_local_url(continuation)
                else url_for("portal.dashboard")
            )
            establish_session(user, False)
            record_login(user.username, user, True, "verified_registration")
            record_audit(
                "account.register",
                "user",
                str(user.id),
                "邮箱验证完成并创建baka网关账号",
            )
            db.session.commit()
            flash("邮箱验证完成，baka网关账号已经创建。", "success")
            return redirect(target)
        db.session.commit()
        messages = {
            "expired": "验证码已经过期，请重新发送。",
            "locked": "验证码已失效或尝试次数已用完，请重新发送。",
            "consumed": "验证码已经使用，请重新发送。",
            "invalid": "验证码不正确，请检查后重试。",
        }
        flash(messages.get(result.status, "验证码无法使用，请重新发送。"), "error")
        return redirect(url_for("auth.registration_email_verification"))
    if request.method == "POST":
        flash(form.code.errors[0], "error")
        return redirect(url_for("auth.registration_email_verification"))
    return _render_email_verification(
        verification_mode="registration",
        recipient=recipient,
        challenge=challenge,
        form=form,
    )


@auth_bp.post("/register/verify-email/resend/")
def registration_email_resend():
    if not EmptyForm().validate_on_submit():
        abort(400)
    if current_user.is_authenticated:
        return redirect(url_for("portal.dashboard"))
    if not _registration_enabled():
        flash("管理员暂时关闭了新账号邮箱验证。", "error")
        return redirect(url_for("auth.login"))
    pending = _pending_registration()
    if pending is None:
        flash("注册验证已经过期，请重新填写注册资料。", "info")
        return redirect(url_for("auth.register"))
    try:
        _deliver_email_challenge(
            "register",
            pending.get_email(),
            "registration",
            pending_registration_id=pending.id,
            fingerprint_scope="registration-email",
        )
    except ChallengeRateLimited as error:
        db.session.rollback()
        flash(f"发送过于频繁，请在 {error.retry_after} 秒后再试。", "error")
    except MailDeliveryError as error:
        db.session.rollback()
        record_audit(
            "account.register.email.send",
            "pending_registration",
            "existing",
            f"result=failed;code={error.code}",
        )
        db.session.commit()
        flash(error.public_message, "error")
    else:
        record_audit(
            "account.register.email.send",
            "pending_registration",
            "existing",
            "result=success",
        )
        db.session.commit()
        flash("新的验证码已经发送。", "success")
    return redirect(url_for("auth.registration_email_verification"))


@auth_bp.route("/forgot-password/", methods=["GET", "POST"])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = _find_user(form.identifier.data)
        if user and user.is_active and user.email:
            try:
                _deliver_email_challenge(
                    "password_reset",
                    user.email,
                    "account",
                    user_id=user.id,
                    fingerprint_scope="password-reset-verification",
                )
            except ChallengeRateLimited as error:
                db.session.rollback()
                flash(f"发送过于频繁，请在 {error.retry_after} 秒后再试。", "error")
            except MailDeliveryError as error:
                db.session.rollback()
                record_audit(
                    "account.password.recovery.request",
                    "user",
                    str(user.id),
                    "result=accepted",
                )
                record_audit(
                    "account.password.recovery.send",
                    "user",
                    str(user.id),
                    f"result=failed;code={error.code}",
                )
                db.session.commit()
                flash(error.public_message, "error")
            else:
                session["password_reset_user_id"] = user.id
                session["password_reset_pending_email"] = user.email
                record_audit(
                    "account.password.recovery.request",
                    "user",
                    str(user.id),
                    "result=accepted",
                )
                record_audit(
                    "account.password.recovery.send",
                    "user",
                    str(user.id),
                    "result=success",
                )
                db.session.commit()
                flash("如果账号存在且已绑定邮箱，找回密码的验证码已经发送。", "success")
                return redirect(url_for("auth.reset_requested"))
        elif user and user.is_active:
            record_audit(
                "account.password.recovery.request",
                "user",
                str(user.id),
                "result=no_email",
            )
            db.session.commit()
            flash("该账号未绑定邮箱，无法通过邮箱找回密码。", "info")
        else:
            # Always show success message to avoid email enumeration
            flash("如果账号存在且已绑定邮箱，找回密码验证码已经发送。", "success")
        return redirect(url_for("auth.forgot_password"))
    return render_template("auth/forgot_password.html", form=form)


@auth_bp.route("/reset-requested/", methods=["GET", "POST"])
def reset_requested():
    # Check if this is a password reset request with email challenge
    user_id = session.get("password_reset_user_id")
    if user_id:
        user = db.session.get(User, user_id)
        if user and user.email:
            pending_email = session.get("password_reset_pending_email")
            recipient = pending_email or user.email
        else:
            user = None
            recipient = None
        user_id_to_check = user.id if user else None
    else:
        user = None
        recipient = None
        user_id_to_check = None
    
    challenge = _latest_email_challenge(
        "password_reset",
        recipient or "",
        user_id=user_id_to_check,
    )
    form = EmailVerificationForm()
    resend_form = EmptyForm()
    if request.method == "POST" and form.validate_on_submit():
        if not user_id or not recipient:
            flash("请重新提交找回密码申请。", "error")
            return redirect(url_for("auth.forgot_password"))
        if challenge is None:
            flash("请先重新发送邮箱验证码。", "error")
            return redirect(url_for("auth.reset_requested"))
        result = consume_email_challenge(
            challenge.public_id,
            "password_reset",
            form.code.data,
        )
        if result.verified:
            record_audit(
                "account.password.recovery.verify",
                "user",
                str(user_id),
                "result=success",
            )
            db.session.commit()
            flash("邮箱验证成功，请输入新密码。", "success")
            session["password_reset_user_id_confirmed"] = user_id
            session.pop("password_reset_pending_email", None)
            return redirect(url_for("auth.password_reset_confirm"))
        db.session.commit()
        messages = {
            "expired": "验证码已经过期，请重新发送。",
            "locked": "验证码已失效或尝试次数已用完，请重新发送。",
            "consumed": "验证码已经使用，请重新发送。",
            "invalid": "验证码不正确，请检查后重试。",
        }
        flash(messages.get(result.status, "验证码无法使用，请重新发送。"), "error")
        return redirect(url_for("auth.reset_requested"))
    if request.method == "POST" and resend_form.validate_on_submit():
        if not user_id or not recipient:
            abort(400)
        try:
            _deliver_email_challenge(
                "password_reset",
                recipient,
                "account",
                user_id=user_id_to_check,
                fingerprint_scope="password-reset-verification",
            )
        except ChallengeRateLimited as error:
            db.session.rollback()
            flash(f"发送过于频繁，请在 {error.retry_after} 秒后再试。", "error")
        except MailDeliveryError as error:
            db.session.rollback()
            record_audit(
                "account.password.recovery.send",
                "user",
                str(user_id),
                f"result=failed;code={error.code}",
            )
            db.session.commit()
            flash(error.public_message, "error")
        else:
            record_audit(
                "account.password.recovery.send",
                "user",
                str(user_id),
                "result=success",
            )
            db.session.commit()
            flash("新的验证码已经发送。", "success")
        return redirect(url_for("auth.reset_requested"))
    if request.method == "POST":
        flash(form.code.errors[0], "error")
        return redirect(url_for("auth.reset_requested"))
    return _render_email_verification(
        verification_mode="password_reset",
        recipient=recipient or "",
        challenge=challenge,
        form=form,
        resend_form=resend_form,
        back_url=url_for("auth.forgot_password"),
    )


@auth_bp.post("/logout/")
@login_required
def logout():
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    item = current_gateway_session()
    if item:
        revoke_session(item)
    record_audit("account.logout", "session", str(item.id if item else ""), "主动退出")
    db.session.commit()
    logout_user()
    session.clear()
    flash("已经安全退出。", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/profile/", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "GET":
        return redirect(url_for("portal.profile"))
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        username = form.username.data.strip().lower()
        duplicate_username = db.session.scalar(
            db.select(User).where(User.username == username, User.id != current_user.id)
        )
        avatar_file = form.avatar.data
        avatar_payload = b""
        avatar_extension = None
        if avatar_file and avatar_file.filename:
            avatar_payload = avatar_file.stream.read(AVATAR_MAX_BYTES + 1)
            avatar_extension = _avatar_extension(avatar_payload)
            if len(avatar_payload) > AVATAR_MAX_BYTES:
                form.avatar.errors.append("头像不能超过2MB。")
            elif avatar_extension is None:
                form.avatar.errors.append("头像仅支持PNG、JPEG或WebP图片。")
        if duplicate_username:
            form.username.errors.append("这个baka网关 ID 已经被使用。")
        if not any(field.errors for field in form):
            previous_avatar = current_user.avatar_filename
            current_user.username = username
            current_user.display_name = form.display_name.data.strip()
            if form.remove_avatar.data:
                current_user.avatar_filename = None
            if avatar_payload and avatar_extension:
                current_user.avatar_filename = (
                    f"user-{current_user.id}-{secrets.token_hex(12)}{avatar_extension}"
                )
                (_avatar_directory() / current_user.avatar_filename).write_bytes(
                    avatar_payload
                )
            if previous_avatar != current_user.avatar_filename:
                _delete_avatar(previous_avatar)
            changed_fields = ["baka网关 ID", "昵称"]
            if previous_avatar != current_user.avatar_filename:
                changed_fields.append("头像")
            record_audit(
                "account.profile.update",
                "user",
                str(current_user.id),
                f"更新个人资料：{'、'.join(changed_fields)}",
            )
            db.session.commit()
            flash("个人资料已经保存。", "success")
            return redirect(url_for("portal.profile"))
    for field in form:
        if field.errors:
            flash(field.errors[0], "error")
            break
    return redirect(url_for("portal.profile"))


@auth_bp.post("/change-email/request/")
@login_required
def request_email_change():
    if not EmptyForm().validate_on_submit():
        abort(400)
    if not effective_email_features()["profile_verification"]:
        flash("管理员暂未开放已有账号邮箱验证。", "error")
        return redirect(url_for("portal.security"))
    form = ChangeEmailRequestForm()
    if form.validate_on_submit():
        new_email = form.new_email.data.strip().lower()
        # Check if this email is already used by another user
        duplicate_user = db.session.scalar(
            db.select(User).where(User.email == new_email, User.id != current_user.id)
        )
        if duplicate_user is not None:
            form.new_email.errors.append("这个邮箱已经被其他账号使用。")
        # Check if pending change already exists for this email
        existing_pending = db.session.scalar(
            db.select(PendingEmailChange).where(
                PendingEmailChange.user_id == current_user.id,
                PendingEmailChange.consumed_at.is_(None),
                PendingEmailChange.invalidated_at.is_(None),
            )
        )
        if existing_pending is not None:
            form.new_email.errors.append("已有待处理的邮箱变更请求，请先完成验证或等待过期。")
        if not form.new_email.errors:
            # Create pending record for new email
            pending_change = PendingEmailChange(
                public_id=new_token(24),
                user_id=current_user.id,
                old_email_digest=recipient_digest(current_user.email or ""),
                expires_at=datetime.now(UTC) + PENDING_REGISTRATION_TTL,
            )
            pending_change.set_new_email(new_email)
            db.session.add(pending_change)
            try:
                db.session.flush()
                _deliver_email_challenge(
                    "change_email",
                    new_email,
                    "account",
                    user_id=current_user.id,
                    fingerprint_scope="change-email-verification",
                )
            except ChallengeRateLimited as error:
                db.session.rollback()
                flash(f"发送过于频繁，请在 {error.retry_after} 秒后再试。", "error")
            except MailDeliveryError as error:
                db.session.rollback()
                record_audit(
                    "account.email.change.send",
                    "user",
                    str(current_user.id),
                    f"result=failed;code={error.code}",
                )
                db.session.commit()
                flash(error.public_message, "error")
            else:
                record_audit(
                    "account.email.change.send",
                    "user",
                    str(current_user.id),
                    "result=success",
                )
                db.session.commit()
                session[PENDING_EMAIL_CHANGE_SESSION_KEY] = pending_change.public_id
                flash("验证码已经发送到新邮箱，请完成验证以替换当前邮箱。", "success")
                return redirect(url_for("auth.change_email_verification"))
    for field in form:
        if field.errors:
            flash(field.errors[0], "error")
            break
    return redirect(url_for("portal.security"))


@auth_bp.post("/verify-email/request/")
@login_required
def request_email_verification():
    if not EmptyForm().validate_on_submit():
        abort(400)
    if current_user.email_verified:
        flash("当前邮箱已经完成验证。", "info")
        return redirect(url_for("portal.security"))
    if not current_user.email:
        flash("请先填写需要验证的邮箱。", "error")
        return redirect(url_for("portal.security"))
    if not effective_email_features()["profile_verification"]:
        flash("管理员暂未开放已有账号邮箱验证。", "error")
        return redirect(url_for("portal.security"))
    try:
        _deliver_email_challenge(
            "verify_email",
            current_user.email,
            "account",
            user_id=current_user.id,
            fingerprint_scope="account-email-verification",
        )
    except ChallengeRateLimited as error:
        db.session.rollback()
        flash(f"发送过于频繁，请在 {error.retry_after} 秒后再试。", "error")
    except MailDeliveryError as error:
        db.session.rollback()
        record_audit(
            "account.email.verification.send",
            "user",
            str(current_user.id),
            f"result=failed;code={error.code}",
        )
        db.session.commit()
        flash(error.public_message, "error")
        return redirect(url_for("portal.security"))
    else:
        record_audit(
            "account.email.verification.send",
            "user",
            str(current_user.id),
            "result=success",
        )
        db.session.commit()
        flash("验证码已经发送到当前邮箱。", "success")
    return redirect(url_for("auth.verify_current_email"))


@auth_bp.route("/verify-email/", methods=["GET", "POST"])
@login_required
def verify_current_email():
    if current_user.email_verified:
        flash("当前邮箱已经完成验证。", "info")
        return redirect(url_for("portal.security"))
    if not current_user.email:
        flash("请先填写需要验证的邮箱。", "error")
        return redirect(url_for("portal.security"))
    if not effective_email_features()["profile_verification"]:
        flash("管理员暂未开放已有账号邮箱验证。", "error")
        return redirect(url_for("portal.security"))
    challenge = _latest_email_challenge(
        "verify_email",
        current_user.email,
        user_id=current_user.id,
    )
    form = EmailVerificationForm()
    if form.validate_on_submit():
        if challenge is None:
            flash("请先重新发送邮箱验证码。", "error")
            return redirect(url_for("auth.verify_current_email"))
        result = consume_email_challenge(
            challenge.public_id,
            "verify_email",
            form.code.data,
        )
        if result.verified:
            current_user.email_verified = True
            record_audit(
                "account.email.verification.complete",
                "user",
                str(current_user.id),
                "result=success",
            )
            db.session.commit()
            flash("当前邮箱验证完成。", "success")
            return redirect(url_for("portal.security"))
        db.session.commit()
        messages = {
            "expired": "验证码已经过期，请重新发送。",
            "locked": "验证码已失效或尝试次数已用完，请重新发送。",
            "consumed": "验证码已经使用，请重新发送。",
            "invalid": "验证码不正确，请检查后重试。",
        }
        flash(messages.get(result.status, "验证码无法使用，请重新发送。"), "error")
        return redirect(url_for("auth.verify_current_email"))
    if request.method == "POST":
        flash(form.code.errors[0], "error")
        return redirect(url_for("auth.verify_current_email"))
    return _render_email_verification(
        verification_mode="account",
        recipient=current_user.email,
        challenge=challenge,
        form=form,
    )


@auth_bp.get("/media/avatar/<path:filename>")
def avatar(filename: str):
    safe_name = Path(filename).name
    if safe_name != filename:
        abort(404)
    return send_from_directory(_avatar_directory(), safe_name, max_age=300)


@auth_bp.route("/security/totp/", methods=["GET", "POST"])
@login_required
def totp_setup():
    if request.method == "GET":
        return redirect(url_for("portal.security"))
    form = TwoFactorForm()
    if not current_user.totp_secret:
        current_user.totp_secret = generate_totp_secret()
        db.session.commit()
    if form.validate_on_submit():
        if verify_totp(current_user.totp_secret, form.code.data):
            current_user.totp_enabled = True
            record_audit("account.totp.enable", "user", str(current_user.id), "启用双重验证")
            db.session.commit()
            flash("双重验证已经启用。", "success")
            return redirect(url_for("portal.security"))
        flash("验证码不正确，请重试。", "error")
    return redirect(url_for("portal.security"))


@auth_bp.get("/security/totp/qr.png")
@login_required
def totp_qr():
    if not current_user.totp_secret:
        abort(404)
    uri = (
        f"otpauth://totp/{quote(current_app.config['APP_NAME_EN'])}:"
        f"{quote(current_user.email or current_user.username)}?secret={current_user.totp_secret}"
        f"&issuer={quote(current_app.config['APP_NAME_EN'])}&digits=6&period=30"
    )
    code = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    code.add_data(uri)
    code.make(fit=True)
    image = code.make_image(image_factory=PyPNGImage)
    stream = io.BytesIO()
    image.save(stream)
    stream.seek(0)
    response = send_file(
        stream,
        mimetype="image/png",
        max_age=0,
        download_name="cloudgate-2fa.png",
    )
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    return response


@auth_bp.post("/security/totp/disable/")
@login_required
def totp_disable():
    if not EmptyForm().validate_on_submit():
        abort(400)
    current_user.totp_enabled = False
    current_user.totp_secret = None
    record_audit(
        "account.totp.disable",
        "user",
        str(current_user.id),
        "关闭双重验证并作废旧密钥",
    )
    db.session.commit()
    flash("双重验证已经关闭，旧二维码和密钥均已作废。", "info")
    return redirect(url_for("portal.security"))


@auth_bp.route("/change-email/verify/", methods=["GET", "POST"])
@login_required
def change_email_verification():
    pending = _pending_email_change()
    if pending is None:
        flash("没有待处理的邮箱变更请求。", "info")
        return redirect(url_for("portal.security"))

    recipient = pending.get_new_email()
    challenge = _latest_email_challenge(
        "change_email",
        recipient,
        user_id=current_user.id,
    )
    form = EmailVerificationForm()
    if form.validate_on_submit():
        if challenge is None:
            flash("请先重新发送邮箱验证码。", "error")
            return redirect(url_for("auth.change_email_verification"))
        result = consume_email_challenge(
            challenge.public_id,
            "change_email",
            form.code.data,
        )
        if result.verified:
            # Verify that new email is not used by another user
            duplicate_user = db.session.scalar(
                db.select(User).where(User.email == recipient, User.id != current_user.id)
            )
            if duplicate_user is not None:
                # Invalidate the pending change
                pending.invalidated_at = datetime.now(UTC)
                db.session.commit()
                flash("邮箱地址已经被其他账号占用，变更已取消。", "error")
                session.pop(PENDING_EMAIL_CHANGE_SESSION_KEY, None)
                return redirect(url_for("portal.security"))
            
            # Replace old email digest
            pending.old_email_digest = recipient_digest(current_user.email or "")
            # Update user email and verify it
            current_user.email = recipient
            current_user.email_verified = True
            pending.consumed_at = datetime.now(UTC)
            record_audit(
                "account.email.change.complete",
                "user",
                str(current_user.id),
                "result=success",
            )
            db.session.commit()
            flash("邮箱验证完成，当前邮箱已经更新。", "success")
            session.pop(PENDING_EMAIL_CHANGE_SESSION_KEY, None)
            return redirect(url_for("portal.security"))
        db.session.commit()
        messages = {
            "expired": "验证码已经过期，请重新发送。",
            "locked": "验证码已失效或尝试次数已用完，请重新发送。",
            "consumed": "验证码已经使用，请重新发送。",
            "invalid": "验证码不正确，请检查后重试。",
        }
        flash(messages.get(result.status, "验证码无法使用，请重新发送。"), "error")
        return redirect(url_for("auth.change_email_verification"))
    if request.method == "POST":
        flash(form.code.errors[0], "error")
        return redirect(url_for("auth.change_email_verification"))
    return _render_email_verification(
        verification_mode="change_email",
        recipient=recipient,
        challenge=challenge,
        form=form,
    )


@auth_bp.post("/change-email/verify/resend/")
@login_required
def change_email_resend():
    if not EmptyForm().validate_on_submit():
        abort(400)
    pending = _pending_email_change()
    if pending is None:
        flash("邮箱变更请求已经过期，请重新提交。", "info")
        return redirect(url_for("portal.security"))
    try:
        _deliver_email_challenge(
            "change_email",
            pending.get_new_email(),
            "account",
            user_id=current_user.id,
            fingerprint_scope="change-email-verification",
        )
    except ChallengeRateLimited as error:
        db.session.rollback()
        flash(f"发送过于频繁，请在 {error.retry_after} 秒后再试。", "error")
    except MailDeliveryError as error:
        db.session.rollback()
        db.session.delete(pending)
        record_audit(
            "account.email.change.send",
            "user",
            str(current_user.id),
            f"result=failed;code={error.code}",
        )
        db.session.commit()
        flash(error.public_message, "error")
    else:
        record_audit(
            "account.email.change.send",
            "user",
            str(current_user.id),
            "result=success",
        )
        db.session.commit()
        flash("新的验证码已经发送到新邮箱。", "success")
    return redirect(url_for("auth.change_email_verification"))


@auth_bp.route("/password-reset-confirm/", methods=["GET", "POST"])
def password_reset_confirm():
    user_id = session.get("password_reset_user_id_confirmed")
    if not user_id:
        flash("请先提交找回密码申请并完成邮箱验证。", "error")
        return redirect(url_for("auth.forgot_password"))
    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        flash("账号不存在或已停用。", "error")
        session.pop("password_reset_user_id_confirmed", None)
        session.pop("pending_password_reset_challenge_public_id", None)
        return redirect(url_for("auth.forgot_password"))
    form = PasswordResetConfirmForm()
    if form.validate_on_submit():
        # Revoke all sessions and OAuth tokens
        from app.services.auth import revoke_user_access
        revoke_user_access(user.id, "password_reset")
        # Set new password
        user.set_password(form.new_password.data)
        record_audit(
            "account.password.reset",
            "user",
            str(user.id),
            "result=success",
        )
        db.session.commit()
        flash("密码已经重置。请使用新密码登录。", "success")
        session.pop("password_reset_user_id_confirmed", None)
        session.pop("pending_password_reset_challenge_public_id", None)
        return redirect(url_for("auth.login"))
    return render_template(
        "auth/password_reset_confirm.html",
        form=form,
        user=user,
        auth_centered=True,
    )
