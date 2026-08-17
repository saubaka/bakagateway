from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from flask import current_app
from sqlalchemy import case

from app.extensions import db
from app.models import EmailChallenge, PendingEmailChange, PendingRegistration
from app.security import new_token

EMAIL_CHALLENGE_PURPOSES = frozenset({"register", "verify_email", "change_email", "password_reset"})


class EmailSecurityError(RuntimeError):
    """Base exception for the email verification security boundary."""


class SensitiveDataError(EmailSecurityError):
    """Raised when encrypted application data cannot be authenticated."""


class ChallengeRateLimited(EmailSecurityError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Email challenge request is rate limited.")
        self.retry_after = max(1, int(retry_after))


@dataclass(frozen=True)
class EmailChallengePolicy:
    ttl_seconds: int = 10 * 60
    resend_seconds: int = 60
    max_attempts: int = 5
    recipient_hourly_limit: int = 6
    recipient_daily_limit: int = 20
    fingerprint_hourly_limit: int = 20
    fingerprint_daily_limit: int = 50


@dataclass(frozen=True)
class ChallengeVerificationResult:
    status: str
    challenge: EmailChallenge | None = None

    @property
    def verified(self) -> bool:
        return self.status == "verified"


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    return current.replace(tzinfo=UTC) if current.tzinfo is None else current.astimezone(UTC)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def _derived_key(label: str) -> bytes:
    if not label or len(label) > 100:
        raise ValueError("A short key-derivation label is required.")
    secret = str(current_app.secret_key or "").encode("utf-8")
    if len(secret) < 32:
        raise EmailSecurityError("The application secret is too short for email security.")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"cloudgate-email-security-v1",
        info=label.encode("utf-8"),
    ).derive(secret)


def encrypt_sensitive_value(value: str, purpose: str) -> str:
    if not isinstance(value, str):
        raise TypeError("Sensitive values must be text.")
    nonce = secrets.token_bytes(12)
    associated_data = f"cloudgate:v1:{purpose}".encode()
    ciphertext = AESGCM(_derived_key(f"aes-gcm:{purpose}")).encrypt(
        nonce,
        value.encode("utf-8"),
        associated_data,
    )
    return f"v1.{_b64encode(nonce)}.{_b64encode(ciphertext)}"


def decrypt_sensitive_value(envelope: str, purpose: str) -> str:
    try:
        version, encoded_nonce, encoded_ciphertext = envelope.split(".", 2)
        if version != "v1":
            raise ValueError
        associated_data = f"cloudgate:v1:{purpose}".encode()
        plaintext = AESGCM(_derived_key(f"aes-gcm:{purpose}")).decrypt(
            _b64decode(encoded_nonce),
            _b64decode(encoded_ciphertext),
            associated_data,
        )
        return plaintext.decode("utf-8")
    except (InvalidTag, UnicodeDecodeError, ValueError) as error:
        raise SensitiveDataError("Encrypted application data failed authentication.") from error


def encrypt_smtp_password(password: str) -> str:
    return encrypt_sensitive_value(password, "smtp-password")


def decrypt_smtp_password(envelope: str) -> str:
    return decrypt_sensitive_value(envelope, "smtp-password")


def encrypt_email_address(email: str, context: str) -> str:
    return encrypt_sensitive_value(email.strip().lower(), f"email-address:{context}")


def decrypt_email_address(envelope: str, context: str) -> str:
    return decrypt_sensitive_value(envelope, f"email-address:{context}")


def _keyed_digest(value: str, scope: str) -> str:
    return hmac.new(
        _derived_key(f"hmac:{scope}"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def recipient_digest(email: str) -> str:
    return _keyed_digest(email.strip().lower(), "email-recipient")


def challenge_code_digest(public_id: str, purpose: str, code: str) -> str:
    return _keyed_digest(f"{public_id}|{purpose}|{code}", "email-code")


def generate_email_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _count_challenges(*conditions) -> int:
    return int(
        db.session.scalar(db.select(db.func.count(EmailChallenge.id)).where(*conditions)) or 0
    )


def _enforce_rate_limits(
    *,
    digest: str,
    purpose: str,
    fingerprint: str,
    now: datetime,
    policy: EmailChallengePolicy,
) -> None:
    latest = db.session.scalar(
        db.select(EmailChallenge)
        .where(
            EmailChallenge.recipient_digest == digest,
            EmailChallenge.purpose == purpose,
        )
        .order_by(EmailChallenge.created_at.desc())
        .limit(1)
    )
    if latest is not None:
        latest_created = _now(latest.created_at)
        retry_at = latest_created + timedelta(seconds=policy.resend_seconds)
        if retry_at > now:
            raise ChallengeRateLimited((retry_at - now).total_seconds().__ceil__())

    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(days=1)
    recipient_conditions = (
        EmailChallenge.recipient_digest == digest,
        EmailChallenge.purpose == purpose,
    )
    if _count_challenges(*recipient_conditions, EmailChallenge.created_at >= hour_ago) >= (
        policy.recipient_hourly_limit
    ):
        raise ChallengeRateLimited(60 * 60)
    if _count_challenges(*recipient_conditions, EmailChallenge.created_at >= day_ago) >= (
        policy.recipient_daily_limit
    ):
        raise ChallengeRateLimited(24 * 60 * 60)
    if fingerprint:
        fingerprint_conditions = (EmailChallenge.request_fingerprint == fingerprint,)
        if (
            _count_challenges(
                *fingerprint_conditions,
                EmailChallenge.created_at >= hour_ago,
            )
            >= policy.fingerprint_hourly_limit
        ):
            raise ChallengeRateLimited(60 * 60)
        if (
            _count_challenges(
                *fingerprint_conditions,
                EmailChallenge.created_at >= day_ago,
            )
            >= policy.fingerprint_daily_limit
        ):
            raise ChallengeRateLimited(24 * 60 * 60)


def issue_email_challenge(
    purpose: str,
    recipient: str,
    *,
    user_id: int | None = None,
    pending_registration_id: int | None = None,
    request_fingerprint: str = "",
    policy: EmailChallengePolicy | None = None,
    now: datetime | None = None,
) -> tuple[EmailChallenge, str]:
    if purpose not in EMAIL_CHALLENGE_PURPOSES:
        raise ValueError("Unsupported email challenge purpose.")
    normalized_recipient = recipient.strip().lower()
    if not normalized_recipient or len(normalized_recipient) > 254:
        raise ValueError("A valid recipient address is required.")
    selected_policy = policy or EmailChallengePolicy()
    if not 1 <= selected_policy.max_attempts <= 20:
        raise ValueError("Email challenge attempts must be between 1 and 20.")
    current_time = _now(now)
    digest = recipient_digest(normalized_recipient)
    _enforce_rate_limits(
        digest=digest,
        purpose=purpose,
        fingerprint=request_fingerprint,
        now=current_time,
        policy=selected_policy,
    )

    db.session.execute(
        db.update(EmailChallenge)
        .where(
            EmailChallenge.recipient_digest == digest,
            EmailChallenge.purpose == purpose,
            EmailChallenge.consumed_at.is_(None),
            EmailChallenge.invalidated_at.is_(None),
        )
        .values(invalidated_at=current_time)
        .execution_options(synchronize_session=False)
    )
    public_id = new_token(24)
    code = generate_email_code()
    challenge = EmailChallenge(
        public_id=public_id,
        purpose=purpose,
        user_id=user_id,
        pending_registration_id=pending_registration_id,
        recipient_digest=digest,
        recipient_ciphertext=encrypt_email_address(
            normalized_recipient,
            "email-challenge",
        ),
        code_digest=challenge_code_digest(public_id, purpose, code),
        request_fingerprint=request_fingerprint[:64],
        max_attempts=selected_policy.max_attempts,
        expires_at=current_time + timedelta(seconds=selected_policy.ttl_seconds),
        created_at=current_time,
    )
    db.session.add(challenge)
    db.session.flush()
    return challenge, code


def consume_email_challenge(
    public_id: str,
    purpose: str,
    code: str,
    *,
    now: datetime | None = None,
) -> ChallengeVerificationResult:
    current_time = _now(now)
    clean_code = "".join(character for character in code if character.isdigit())
    candidate_digest = (
        challenge_code_digest(public_id, purpose, clean_code)
        if purpose in EMAIL_CHALLENGE_PURPOSES and len(clean_code) == 6
        else ""
    )
    if candidate_digest:
        consumed = db.session.execute(
            db.update(EmailChallenge)
            .where(
                EmailChallenge.public_id == public_id,
                EmailChallenge.purpose == purpose,
                EmailChallenge.code_digest == candidate_digest,
                EmailChallenge.consumed_at.is_(None),
                EmailChallenge.invalidated_at.is_(None),
                EmailChallenge.expires_at > current_time,
                EmailChallenge.attempt_count < EmailChallenge.max_attempts,
            )
            .values(consumed_at=current_time)
            .execution_options(synchronize_session=False)
        )
        if consumed.rowcount == 1:
            db.session.expire_all()
            challenge = db.session.scalar(
                db.select(EmailChallenge).where(EmailChallenge.public_id == public_id)
            )
            return ChallengeVerificationResult("verified", challenge)

    challenge = db.session.scalar(
        db.select(EmailChallenge).where(
            EmailChallenge.public_id == public_id,
            EmailChallenge.purpose == purpose,
        )
    )
    if challenge is None:
        return ChallengeVerificationResult("invalid")
    if challenge.consumed_at is not None:
        return ChallengeVerificationResult("consumed", challenge)
    if challenge.invalidated_at is not None or challenge.attempt_count >= challenge.max_attempts:
        return ChallengeVerificationResult("locked", challenge)
    if _now(challenge.expires_at) <= current_time:
        db.session.execute(
            db.update(EmailChallenge)
            .where(
                EmailChallenge.id == challenge.id,
                EmailChallenge.invalidated_at.is_(None),
            )
            .values(invalidated_at=current_time)
            .execution_options(synchronize_session=False)
        )
        return ChallengeVerificationResult("expired", challenge)

    failed = db.session.execute(
        db.update(EmailChallenge)
        .where(
            EmailChallenge.id == challenge.id,
            EmailChallenge.consumed_at.is_(None),
            EmailChallenge.invalidated_at.is_(None),
            EmailChallenge.expires_at > current_time,
            EmailChallenge.attempt_count < EmailChallenge.max_attempts,
        )
        .values(
            attempt_count=EmailChallenge.attempt_count + 1,
            invalidated_at=case(
                (
                    EmailChallenge.attempt_count + 1 >= EmailChallenge.max_attempts,
                    current_time,
                ),
                else_=EmailChallenge.invalidated_at,
            ),
        )
        .execution_options(synchronize_session=False)
    )
    db.session.expire_all()
    challenge = db.session.get(EmailChallenge, challenge.id)
    if failed.rowcount != 1 or challenge.invalidated_at is not None:
        return ChallengeVerificationResult("locked", challenge)
    return ChallengeVerificationResult("invalid", challenge)


def purge_expired_email_security_records(*, now: datetime | None = None) -> dict[str, int]:
    current_time = _now(now)
    deleted_challenges = db.session.execute(
        db.delete(EmailChallenge)
        .where(
            db.or_(
                EmailChallenge.expires_at < current_time - timedelta(days=1),
                EmailChallenge.consumed_at < current_time - timedelta(days=1),
                EmailChallenge.invalidated_at < current_time - timedelta(days=1),
            )
        )
        .execution_options(synchronize_session=False)
    ).rowcount
    deleted_pending = db.session.execute(
        db.delete(PendingRegistration)
        .where(
            PendingRegistration.completed_at.is_(None),
            PendingRegistration.expires_at < current_time,
        )
        .execution_options(synchronize_session=False)
    ).rowcount
    deleted_email_changes = db.session.execute(
        db.delete(PendingEmailChange)
        .where(
            db.or_(
                PendingEmailChange.expires_at < current_time,
                PendingEmailChange.consumed_at < current_time - timedelta(days=1),
                PendingEmailChange.invalidated_at < current_time - timedelta(days=1),
            )
        )
        .execution_options(synchronize_session=False)
    ).rowcount
    return {
        "email_challenges": int(deleted_challenges or 0),
        "pending_registrations": int(deleted_pending or 0),
        "pending_email_changes": int(deleted_email_changes or 0),
    }
