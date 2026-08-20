from __future__ import annotations

import ipaddress
import smtplib
import ssl
from contextlib import suppress
from datetime import UTC, datetime
from email.message import EmailMessage

from flask import current_app

from app.extensions import db
from app.models import MailProvider
from app.services.email_templates import render_email_template


class MailDeliveryError(RuntimeError):
    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


def is_loopback_smtp_host(host: str) -> bool:
    normalized = host.strip().lower().strip("[]")
    if normalized in {"localhost", "localhost.localdomain"} or normalized.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _safe_header(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if "\r" in cleaned or "\n" in cleaned:
        raise MailDeliveryError("invalid_configuration", f"{field_name}包含无效换行。")
    return cleaned


def _open_connection(provider: MailProvider):
    if provider.security_mode == "plain" and not is_loopback_smtp_host(provider.host):
        raise MailDeliveryError(
            "insecure_transport",
            "无加密SMTP只允许连接本机地址。",
        )
    context = ssl.create_default_context()
    connection = None
    try:
        if provider.security_mode == "ssl":
            connection = smtplib.SMTP_SSL(
                provider.host,
                provider.port,
                timeout=provider.timeout_seconds,
                context=context,
            )
        else:
            connection = smtplib.SMTP(
                provider.host,
                provider.port,
                timeout=provider.timeout_seconds,
            )
            connection.ehlo()
            if provider.security_mode == "starttls":
                connection.starttls(context=context)
                connection.ehlo()
        if provider.username:
            connection.login(provider.username, provider.get_password())
        return connection
    except Exception as error:
        if connection is not None:
            _close_connection(connection)
        if isinstance(error, MailDeliveryError):
            raise
        if isinstance(error, smtplib.SMTPAuthenticationError):
            raise MailDeliveryError("authentication_failed", "SMTP账号或密码验证失败。") from error
        if isinstance(error, TimeoutError):
            raise MailDeliveryError("timeout", "连接邮件服务器超时。") from error
        if isinstance(error, ssl.SSLError):
            raise MailDeliveryError("tls_failed", "邮件服务器的安全连接验证失败。") from error
        if isinstance(
            error,
            (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, OSError),
        ):
            raise MailDeliveryError("connection_failed", "无法连接邮件服务器。") from error
        if isinstance(error, smtplib.SMTPException):
            raise MailDeliveryError("protocol_failed", "邮件服务器没有接受连接请求。") from error
        raise MailDeliveryError("invalid_configuration", "邮件服务配置无法使用。") from error


def _close_connection(connection) -> None:
    with suppress(smtplib.SMTPException, OSError):
        connection.quit()


def _new_message(provider: MailProvider, recipient: str, subject: str) -> EmailMessage:
    message = EmailMessage()
    sender_name = _safe_header(provider.sender_name, "发件人名称")
    sender_email = _safe_header(provider.sender_email, "发件邮箱")
    target = _safe_header(recipient, "收件邮箱")
    message["Subject"] = _safe_header(subject, "邮件主题")
    message["From"] = f"{sender_name} <{sender_email}>" if sender_name else sender_email
    message["To"] = target
    if provider.reply_to:
        message["Reply-To"] = _safe_header(provider.reply_to, "回复邮箱")
    return message


def _send_message(
    provider: MailProvider,
    message: EmailMessage,
    *,
    recipient_refused_message: str,
    send_failed_message: str,
    timeout_message: str,
) -> None:
    connection = _open_connection(provider)
    try:
        refused = connection.send_message(message)
        if refused:
            raise MailDeliveryError("recipient_refused", recipient_refused_message)
    except TimeoutError as error:
        raise MailDeliveryError("timeout", timeout_message) from error
    except smtplib.SMTPRecipientsRefused as error:
        raise MailDeliveryError("recipient_refused", recipient_refused_message) from error
    except smtplib.SMTPException as error:
        raise MailDeliveryError("send_failed", send_failed_message) from error
    finally:
        _close_connection(connection)


def send_templated_email(
    provider: MailProvider,
    template_key: str,
    recipient: str,
    variables: dict[str, object],
    *,
    recipient_refused_message: str = "收件邮箱被邮件服务器拒绝。",
    send_failed_message: str = "邮件服务器没有接受邮件。",
    timeout_message: str = "发送邮件时等待服务器响应超时。",
) -> None:
    try:
        subject, html_body, text_body = render_email_template(template_key, variables)
    except ValueError as error:
        raise MailDeliveryError("invalid_configuration", str(error)) from error
    message = _new_message(provider, recipient, subject)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    _send_message(
        provider,
        message,
        recipient_refused_message=recipient_refused_message,
        send_failed_message=send_failed_message,
        timeout_message=timeout_message,
    )


def test_mail_provider_connection(provider: MailProvider) -> None:
    connection = _open_connection(provider)
    try:
        status, _message = connection.noop()
        if int(status) >= 400:
            raise MailDeliveryError("protocol_failed", "邮件服务器没有接受连接测试。")
    except TimeoutError as error:
        raise MailDeliveryError("timeout", "邮件服务器响应超时。") from error
    except smtplib.SMTPException as error:
        raise MailDeliveryError("protocol_failed", "邮件服务器没有接受连接测试。") from error
    finally:
        _close_connection(connection)


def send_mail_provider_test(provider: MailProvider, recipient: str) -> None:
    send_templated_email(
        provider,
        "smtp_test",
        recipient,
        {
            "app_name": current_app.config.get("APP_NAME", "baka网关"),
            "provider_name": provider.name,
            "tested_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
        },
        recipient_refused_message="测试收件地址被邮件服务器拒绝。",
        send_failed_message="邮件服务器没有接受测试邮件。",
        timeout_message="发送测试邮件时等待服务器响应超时。",
    )


def send_verification_code(
    provider: MailProvider,
    recipient: str,
    code: str,
    *,
    ttl_minutes: int,
    verification_kind: str = "administrator",
    template_key: str | None = None,
) -> None:
    clean_code = "".join(character for character in code if character.isdigit())
    if len(clean_code) != 6:
        raise MailDeliveryError("invalid_configuration", "验证码内容无效。")
    legacy_template_keys = {
        "administrator": "admin_email_verification",
        "registration": "registration",
        "account": "account_email_verification",
    }
    resolved_template = template_key or legacy_template_keys.get(verification_kind)
    actions = {
        "admin_email_verification": "验证baka网关管理员邮箱",
        "registration": "创建baka网关账号",
        "account_email_verification": "验证baka网关账号的当前邮箱",
        "change_email": "更换baka网关账号邮箱",
        "password_reset": "找回baka网关账号密码",
        "login_verification": "在新设备或新网络验证baka网关账号登录",
    }
    if resolved_template is None or resolved_template not in actions:
        raise MailDeliveryError("invalid_configuration", "验证码邮件类型无效。")
    send_templated_email(
        provider,
        resolved_template,
        recipient,
        {
            "app_name": current_app.config.get("APP_NAME", "baka网关"),
            "action": actions[resolved_template],
            "code": clean_code,
            "ttl_minutes": ttl_minutes,
            "recipient_email": recipient,
            "issuer": current_app.config.get("OIDC_ISSUER", ""),
            "support_email": provider.reply_to or provider.sender_email,
            "current_year": datetime.now(UTC).year,
        },
        recipient_refused_message="验证邮箱被邮件服务器拒绝。",
        send_failed_message="邮件服务器没有接受验证码邮件。",
        timeout_message="发送验证码时等待服务器响应超时。",
    )


def set_default_mail_provider(provider: MailProvider) -> None:
    db.session.execute(
        db.update(MailProvider)
        .where(MailProvider.id != provider.id, MailProvider.is_default.is_(True))
        .values(is_default=False)
        .execution_options(synchronize_session=False)
    )
    provider.is_active = True
    provider.is_default = True


def ensure_default_mail_provider() -> MailProvider | None:
    current = db.session.scalar(
        db.select(MailProvider).where(
            MailProvider.is_default.is_(True),
            MailProvider.is_active.is_(True),
        )
    )
    if current is not None:
        return current
    db.session.execute(
        db.update(MailProvider)
        .where(MailProvider.is_default.is_(True))
        .values(is_default=False)
        .execution_options(synchronize_session=False)
    )
    replacement = db.session.scalar(
        db.select(MailProvider)
        .where(MailProvider.is_active.is_(True))
        .order_by(MailProvider.created_at.asc(), MailProvider.id.asc())
        .limit(1)
    )
    if replacement is not None:
        replacement.is_default = True
    return replacement
