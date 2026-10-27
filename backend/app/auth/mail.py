import ipaddress
import smtplib
import socket
import ssl
from email.message import EmailMessage

from flask import current_app
from sqlalchemy import text

from ..extensions import db
from ..models import MailConfiguration
from .security import AuthError, decrypt, encrypt


def configuration():
    row = db.session.get(MailConfiguration, 1)
    return decrypt(row.encrypted_data, "mail") if row else None


def validate(config):
    if config["security"] not in {"tls", "starttls", "plain"} or not 1 <= config["port"] <= 65535:
        raise ValueError("Invalid SMTP transport")
    if "\r" in config["host"] or "\n" in config["host"] or not config["host"]:
        raise ValueError("Invalid SMTP host")
    if config["security"] == "plain":
        if current_app.config["BG_ENV"] == "production":
            raise ValueError("Production SMTP requires TLS")
        addresses = socket.getaddrinfo(config["host"], config["port"], type=socket.SOCK_STREAM)
        if not all(ipaddress.ip_address(item[4][0]).is_private for item in addresses):
            raise ValueError("Plain SMTP is allowed only on a private local test network")


def connect(config):
    validate(config)
    context = ssl.create_default_context()
    if config["security"] == "tls":
        client = smtplib.SMTP_SSL(config["host"], config["port"], timeout=3, context=context)
    else:
        client = smtplib.SMTP(config["host"], config["port"], timeout=3)
        client.ehlo()
        if config["security"] == "starttls":
            client.starttls(context=context)
            client.ehlo()
    try:
        if config.get("username"):
            client.login(config["username"], config["password"])
    except Exception:
        client.close()
        raise
    return client


def save_configuration(config, *, commit=True):
    db.session.execute(text("SELECT pg_advisory_xact_lock(782341)"))
    validate(config)
    with connect(config):
        pass
    row = db.session.get(MailConfiguration, 1)
    if not row:
        row = MailConfiguration(id=1)
        db.session.add(row)
    row.version = (row.version or 0) + 1
    row.encrypted_data = encrypt(config, "mail")
    if commit:
        db.session.commit()


def send(recipient, *, code=None, notice=False):
    config = configuration()
    if not config:
        raise AuthError("mail_unavailable", "邮件服务尚未配置，请联系管理员。", 503)
    message = EmailMessage()
    message["From"] = config["sender"]
    message["To"] = recipient
    message["Subject"] = (
        "baka 身份平台 · 邮箱变更提醒"
        if notice
        else ("baka 身份平台 · 邮箱验证" if code else "baka 身份平台 · 邮件测试")
    )
    message.set_content(
        "你的账号收到邮箱变更确认请求。如果不是本人操作，请及时联系平台管理员恢复账号。"
        if notice
        else (
            f"你的验证码是：{code}\n验证码在本次流程中10分钟内有效，请勿转发。\n如果不是本人操作，请忽略这封邮件。"
            if code
            else "这是一封邮件服务测试邮件，无需回复。"
        )
    )
    try:
        with connect(config) as client:
            client.send_message(message)
    except (OSError, smtplib.SMTPException, ValueError):
        raise AuthError(
            "mail_unavailable", "邮件暂时无法发送，请稍后重试或联系管理员。", 503
        ) from None
