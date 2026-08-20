from __future__ import annotations

from dataclasses import dataclass

from app.extensions import db
from app.models import MailProvider, Role, User
from app.services.appearance import get_setting, set_setting
from app.services.email_security import EmailChallengePolicy


@dataclass(frozen=True)
class EmailFeaturePolicy:
    registration_enabled: bool = False
    profile_verification_enabled: bool = False
    password_reset_enabled: bool = False
    login_verification_enabled: bool = False
    code_ttl_minutes: int = 10
    resend_seconds: int = 60
    max_attempts: int = 5

    def challenge_policy(self) -> EmailChallengePolicy:
        return EmailChallengePolicy(
            ttl_seconds=self.code_ttl_minutes * 60,
            resend_seconds=self.resend_seconds,
            max_attempts=self.max_attempts,
        )


def _boolean_setting(key: str, default: bool = False) -> bool:
    fallback = "true" if default else "false"
    return get_setting(key, fallback).strip().lower() in {"1", "true", "yes", "on"}


def _integer_setting(key: str, default: int, allowed: frozenset[int]) -> int:
    try:
        value = int(get_setting(key, str(default)))
    except (TypeError, ValueError):
        value = default
    return value if value in allowed else default


def load_email_policy() -> EmailFeaturePolicy:
    return EmailFeaturePolicy(
        registration_enabled=_boolean_setting("email_registration_enabled"),
        profile_verification_enabled=_boolean_setting("email_profile_verification_enabled"),
        password_reset_enabled=_boolean_setting("email_password_reset_enabled"),
        login_verification_enabled=_boolean_setting("email_login_verification_enabled"),
        code_ttl_minutes=_integer_setting("email_code_ttl_minutes", 10, frozenset({5, 10, 15})),
        resend_seconds=_integer_setting("email_resend_seconds", 60, frozenset({60, 90, 120, 300})),
        max_attempts=_integer_setting("email_max_attempts", 5, frozenset({3, 4, 5})),
    )


def save_email_policy(policy: EmailFeaturePolicy) -> None:
    set_setting(
        "email_registration_enabled",
        "true" if policy.registration_enabled else "false",
    )
    set_setting(
        "email_profile_verification_enabled",
        "true" if policy.profile_verification_enabled else "false",
    )
    set_setting(
        "email_password_reset_enabled",
        "true" if policy.password_reset_enabled else "false",
    )
    set_setting(
        "email_login_verification_enabled",
        "true" if policy.login_verification_enabled else "false",
    )
    set_setting("email_code_ttl_minutes", str(policy.code_ttl_minutes))
    set_setting("email_resend_seconds", str(policy.resend_seconds))
    set_setting("email_max_attempts", str(policy.max_attempts))


def record_email_delivery_health(healthy: bool) -> None:
    """Delivery attempts double as health probes for mail-backed login checks."""
    set_setting("email_delivery_health", "ok" if healthy else "failed")


def email_delivery_healthy() -> bool:
    return get_setting("email_delivery_health", "ok").strip().lower() != "failed"


def default_mail_provider() -> MailProvider | None:
    return db.session.scalar(
        db.select(MailProvider).where(
            MailProvider.is_default.is_(True),
            MailProvider.is_active.is_(True),
        )
    )


def verified_administrator_exists() -> bool:
    return (
        db.session.scalar(
            db.select(User.id)
            .join(User.roles)
            .where(
                Role.name == "administrator",
                User.status == "active",
                User.email.is_not(None),
                User.email_verified.is_(True),
            )
            .limit(1)
        )
        is not None
    )


def email_policy_readiness(current_admin: User | None = None) -> dict[str, object]:
    provider = default_mail_provider()
    provider_tested = bool(provider and provider.last_test_succeeded is True)
    verified_admin = verified_administrator_exists()
    current_admin_verified = bool(
        current_admin
        and current_admin.is_active
        and current_admin.has_role("administrator")
        and current_admin.email
        and current_admin.email_verified
    )
    return {
        "provider": provider,
        "provider_configured": provider is not None,
        "provider_tested": provider_tested,
        "verified_administrator_exists": verified_admin,
        "current_administrator_verified": current_admin_verified,
        "ready": bool(provider_tested and verified_admin),
    }


def effective_email_features() -> dict[str, bool]:
    policy = load_email_policy()
    ready = bool(email_policy_readiness()["ready"])
    return {
        "registration": ready and policy.registration_enabled,
        "profile_verification": ready and policy.profile_verification_enabled,
        "password_reset": ready and policy.password_reset_enabled,
        "login_verification": (
            ready
            and policy.login_verification_enabled
            and email_delivery_healthy()
        ),
    }
