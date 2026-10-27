import base64
import hashlib
import hmac
import json
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote, urlsplit

from cryptography.fernet import Fernet
from email_validator import EmailNotValidError, validate_email
from flask import current_app, request
from sqlalchemy.dialects.postgresql import insert
from werkzeug.security import generate_password_hash

from ..extensions import db
from ..models import AuthRate


class AuthError(Exception):
    def __init__(self, code, message, status=400, *, persist=False, retry_after=None):
        self.code, self.message, self.status = code, message, status
        self.persist, self.retry_after = persist, retry_after


def now():
    return datetime.now(UTC)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def keyed(value):
    return hmac.new(current_app.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()


def cipher(purpose):
    key = hmac.new(
        current_app.secret_key.encode(), ("encryption/v1/" + purpose).encode(), hashlib.sha256
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value, purpose):
    return cipher(purpose).encrypt(json.dumps(value, ensure_ascii=False).encode()).decode()


def decrypt(value, purpose):
    return json.loads(cipher(purpose).decrypt(value.encode()))


def username(value):
    value = value.strip().lower() if isinstance(value, str) else ""
    if not re.fullmatch(r"[a-z][a-z0-9_-]{2,31}", value):
        raise AuthError(
            "invalid_request", "账号名需为3至32个字符，以字母开头，可含数字、下划线和短横线。"
        )
    return value


def email(value):
    if not isinstance(value, str) or len(value) > 254:
        raise AuthError("invalid_request", "请输入有效的邮箱地址。")
    try:
        return validate_email(
            value.strip(),
            check_deliverability=False,
            test_environment=current_app.config["BG_ENV"] != "production",
        ).normalized.lower()
    except EmailNotValidError:
        raise AuthError("invalid_request", "请输入有效的邮箱地址。") from None


def password(value, confirmation):
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise AuthError("invalid_request", "密码需要12至128个字符。")
    if value != confirmation:
        raise AuthError("invalid_request", "两次密码不一致。")
    return generate_password_hash(value, method="scrypt:131072:8:1")


def safe_next(value):
    if not isinstance(value, str) or len(value) > 512:
        return "/account"
    decoded = unquote(unquote(value))
    if (
        any(ord(c) < 32 for c in decoded)
        or "\\" in decoded
        or not decoded.startswith("/")
        or decoded.startswith("//")
    ):
        return "/account"
    parsed = urlsplit(decoded)
    if parsed.netloc or parsed.scheme or parsed.fragment:
        return "/account"
    if parsed.path == "/account" or parsed.path.startswith("/account/"):
        return decoded
    if parsed.path in {
        "/admin",
        "/admin/users",
        "/admin/clients",
        "/admin/mail",
        "/admin/settings",
        "/admin/audit",
    }:
        return decoded
    if parsed.path == "/authorize" and re.fullmatch(
        r"[A-Za-z0-9_-]{16,128}", parse_qs(parsed.query).get("tx", [""])[0]
    ):
        return decoded
    return "/account"


def limit(action, identifier="", maximum=12, seconds=900):
    timestamp = now()
    window = int(timestamp.timestamp()) // seconds
    key = keyed(f"rate/v1/{action}/{request.remote_addr}/{identifier}/{window}")
    expires = datetime.fromtimestamp((window + 1) * seconds, UTC)
    statement = insert(AuthRate).values(bucket=key, count=1, expires_at=expires)
    statement = statement.on_conflict_do_update(
        index_elements=[AuthRate.bucket], set_={"count": AuthRate.count + 1}
    ).returning(AuthRate.count)
    # A separate short transaction preserves rate counts even if authentication
    # fails or SMTP rolls back the main request transaction.
    with db.engine.begin() as connection:
        count = connection.execute(statement).scalar_one()
    if count > maximum:
        raise AuthError(
            "rate_limited",
            "操作过于频繁，请稍后重试。",
            429,
            retry_after=max(1, int((expires - timestamp).total_seconds())),
        )


def require_json():
    if not request.is_json:
        raise AuthError("unsupported_media_type", "此请求需要JSON格式。", 415)
    data = request.get_json()
    if not isinstance(data, dict):
        raise AuthError("invalid_request", "请求格式不正确。")
    return data
