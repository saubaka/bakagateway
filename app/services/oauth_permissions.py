"""OAuth permission registry and durable per-user consent helpers."""

from __future__ import annotations

from app.extensions import db
from app.models import UserClientConsent

OPTIONAL_PERMISSION_DEFINITIONS = {
    "profile": {
        "label": "昵称",
        "description": "读取你的baka网关 ID 与当前昵称。",
    },
    "email": {
        "label": "电子邮箱",
        "description": "读取邮箱地址及其验证状态；未填写时不会返回邮箱。",
    },
    "avatar": {
        "label": "头像",
        "description": "读取你在baka网关中设置的圆形头像。",
    },
}


def ordered_optional_scopes(scopes: str | list[str] | set[str]) -> list[str]:
    values = set(scopes.split() if isinstance(scopes, str) else scopes)
    return [name for name in OPTIONAL_PERMISSION_DEFINITIONS if name in values]


def normalized_client_scopes(optional_scopes: list[str] | set[str]) -> str:
    return " ".join(["openid", *ordered_optional_scopes(optional_scopes)])


def get_user_consent(user_id: int, client_id: str) -> UserClientConsent | None:
    return db.session.scalar(
        db.select(UserClientConsent).where(
            UserClientConsent.user_id == user_id,
            UserClientConsent.client_id == client_id,
        )
    )


def save_user_consent(
    user_id: int,
    client_id: str,
    requested_optional: list[str],
    granted_optional: list[str],
) -> UserClientConsent:
    requested = ordered_optional_scopes(requested_optional)
    granted = ordered_optional_scopes(
        set(granted_optional).intersection(requested)
    )
    denied = [name for name in requested if name not in granted]
    item = get_user_consent(user_id, client_id)
    if item is None:
        item = UserClientConsent(user_id=user_id, client_id=client_id)
        db.session.add(item)
    item.granted_scopes = normalized_client_scopes(granted)
    item.denied_scopes = " ".join(denied)
    return item


def effective_token_scopes(
    token_scope: str,
    user_id: int,
    client_id: str,
) -> list[str]:
    token_values = set(token_scope.split())
    item = get_user_consent(user_id, client_id)
    if item is not None:
        token_values.intersection_update(item.granted_scopes.split())
    token_values.add("openid")
    return ["openid", *ordered_optional_scopes(token_values)]
