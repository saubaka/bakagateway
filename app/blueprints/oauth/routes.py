from __future__ import annotations

import base64
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import (
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user

from app.blueprints.oauth import oauth_bp
from app.extensions import csrf, db
from app.forms import ConsentConfirmationForm, ConsentPermissionsForm
from app.models import AuthorizationGrant, GatewayClient, OAuthToken
from app.security import (
    encode_id_token,
    expires_in,
    hash_token,
    new_token,
    public_jwk,
    verify_pkce,
)
from app.services.auth import aware, record_audit
from app.services.oauth_permissions import (
    OPTIONAL_PERMISSION_DEFINITIONS,
    effective_token_scopes,
    get_user_consent,
    ordered_optional_scopes,
    save_user_consent,
)

OAUTH_REVIEW_KEY = "oauth_pending_review"
OAUTH_REVIEW_TTL_SECONDS = 300


def _issuer() -> str:
    return current_app.config["OIDC_ISSUER"]


def _oauth_error(error: str, description: str, status: int = 400):
    response = jsonify(error=error, error_description=description)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    return response


def _append_query(uri: str, values: dict[str, str]) -> str:
    parts = urlsplit(uri)
    existing = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if name not in values
    ]
    query = urlencode([*existing, *values.items()])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _client(client_id: str | None) -> GatewayClient | None:
    if not client_id:
        return None
    return db.session.scalar(
        db.select(GatewayClient).where(
            GatewayClient.client_id == client_id,
            GatewayClient.is_active.is_(True),
        )
    )


def _authenticated_client() -> GatewayClient | None:
    client_id = request.form.get("client_id", "")
    client_secret = request.form.get("client_secret", "")
    header = request.headers.get("Authorization", "")
    if header.startswith("Basic "):
        try:
            decoded = base64.b64decode(header[6:]).decode()
            client_id, client_secret = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return None
    item = _client(client_id)
    return item if item and item.check_secret(client_secret) else None


@oauth_bp.get("/.well-known/openid-configuration")
def discovery():
    issuer = _issuer()
    return jsonify(
        issuer=issuer,
        authorization_endpoint=f"{issuer}/oauth/authorize",
        token_endpoint=f"{issuer}/oauth/token",
        userinfo_endpoint=f"{issuer}/oauth/userinfo",
        jwks_uri=f"{issuer}/oauth/jwks.json",
        revocation_endpoint=f"{issuer}/oauth/revoke",
        introspection_endpoint=f"{issuer}/oauth/introspect",
        response_types_supported=["code"],
        grant_types_supported=["authorization_code", "refresh_token"],
        subject_types_supported=["public"],
        id_token_signing_alg_values_supported=["RS256"],
        scopes_supported=["openid", "profile", "email", "avatar"],
        code_challenge_methods_supported=["S256"],
        token_endpoint_auth_methods_supported=["client_secret_basic", "client_secret_post"],
    )


@oauth_bp.get("/oauth/jwks.json")
def jwks():
    return jsonify(keys=[public_jwk()])


def _authorization_params() -> tuple[GatewayClient | None, dict[str, str], str | None]:
    values = {
        "response_type": request.values.get("response_type", ""),
        "client_id": request.values.get("client_id", ""),
        "redirect_uri": request.values.get("redirect_uri", ""),
        "scope": request.values.get("scope", ""),
        "state": request.values.get("state", ""),
        "nonce": request.values.get("nonce", ""),
        "code_challenge": request.values.get("code_challenge", ""),
        "code_challenge_method": request.values.get("code_challenge_method", ""),
        "screen_hint": request.values.get("screen_hint", ""),
    }
    client = _client(values["client_id"])
    if client is None:
        return None, values, "未知或已停用的客户端。"
    if values["redirect_uri"] not in client.redirect_uris:
        return client, values, "回调地址没有登记。"
    if values["response_type"] != "code":
        return client, values, "只支持授权码模式。"
    if values["code_challenge_method"] != "S256" or not values["code_challenge"]:
        return client, values, "必须使用S256 PKCE。"
    requested = set(values["scope"].split())
    allowed = set(client.scopes.split())
    if "openid" not in requested or not requested.issubset(allowed):
        return client, values, "请求的权限范围不可用。"
    if values["screen_hint"] not in {"", "login", "signup"}:
        return client, values, "无法识别登录界面提示。"
    return client, values, None


def _user_picture(user) -> str:
    if not user.avatar_filename:
        return ""
    return url_for("auth.avatar", filename=user.avatar_filename, _external=True)


def _authorization_return(
    client: GatewayClient,
    values: dict[str, str],
    granted_scope: str,
):
    raw_code = new_token(32)
    grant = AuthorizationGrant(
        code_hash=hash_token(raw_code),
        client_id=client.client_id,
        user_id=current_user.id,
        redirect_uri=values["redirect_uri"],
        scope=granted_scope,
        nonce=values["nonce"] or None,
        code_challenge=values["code_challenge"],
        expires_at=expires_in(current_app.config["AUTHORIZATION_CODE_TTL"]),
    )
    db.session.add(grant)
    record_audit("oauth.authorize", "client", client.client_id, granted_scope)
    db.session.commit()
    return render_template(
        "oauth/returning.html",
        client=client,
        return_url=_append_query(
            values["redirect_uri"],
            {"code": raw_code, "state": values["state"]},
        ),
        countdown_seconds=3,
    )


def _populate_authorization_form(form, values: dict[str, str], stage: str) -> None:
    form.stage.data = stage
    for name in (
        "response_type",
        "client_id",
        "redirect_uri",
        "scope",
        "state",
        "nonce",
        "code_challenge",
        "code_challenge_method",
    ):
        getattr(form, name).data = values[name]


def _permission_view(
    client: GatewayClient,
    values: dict[str, str],
    requested_optional: list[str],
    selected: set[str],
    form: ConsentPermissionsForm | None = None,
):
    supplied_form = form is not None
    form = form or ConsentPermissionsForm()
    if not supplied_form or not form.stage.data:
        _populate_authorization_form(form, values, "permissions")
    return render_template(
        "oauth/authorize.html",
        form=form,
        client=client,
        permissions=[
            {
                "scope": scope,
                **OPTIONAL_PERMISSION_DEFINITIONS[scope],
                "selected": scope in selected,
            }
            for scope in requested_optional
        ],
    )


def _deny_authorization(values: dict[str, str]):
    session.pop(OAUTH_REVIEW_KEY, None)
    return redirect(
        _append_query(
            values["redirect_uri"],
            {"error": "access_denied", "state": values["state"]},
        )
    )


@oauth_bp.route("/oauth/authorize", methods=["GET", "POST"])
def authorize():
    client, values, error = _authorization_params()
    if error:
        if client and values["redirect_uri"] in client.redirect_uris:
            return redirect(
                _append_query(
                    values["redirect_uri"],
                    {"error": "invalid_request", "state": values["state"]},
                )
            )
        abort(400)
    if request.method == "GET" and request.args.get("gateway_checked") != "1":
        return render_template(
            "oauth/session_check.html",
            client=client,
            authenticated=current_user.is_authenticated,
            continue_url=_append_query(request.url, {"gateway_checked": "1"}),
        )
    if not current_user.is_authenticated:
        endpoint = "auth.register" if values["screen_hint"] == "signup" else "auth.login"
        return redirect(url_for(endpoint, next=request.full_path))
    requested_optional = ordered_optional_scopes(values["scope"])
    if request.method == "GET":
        previous = get_user_consent(current_user.id, client.client_id)
        selected = (
            set(previous.granted_scopes.split())
            if previous is not None
            else set(requested_optional)
        )
        return _permission_view(
            client,
            values,
            requested_optional,
            selected,
        )

    stage = request.form.get("stage", "")
    decision = request.form.get("decision", "")
    if decision == "deny":
        denial_form = ConsentConfirmationForm()
        if not denial_form.validate_on_submit():
            abort(400)
        return _deny_authorization(values)

    if stage == "permissions":
        form = ConsentPermissionsForm()
        selected = ordered_optional_scopes(request.form.getlist("permissions"))
        selected = [scope for scope in selected if scope in requested_optional]
        if not form.validate_on_submit():
            return _permission_view(
                client,
                values,
                requested_optional,
                set(selected),
                form,
            )
        if decision != "next":
            abort(400)
        session[OAUTH_REVIEW_KEY] = {
            "user_id": current_user.id,
            "client_id": client.client_id,
            "state": values["state"],
            "values": values,
            "selected": selected,
            "created_at": int(datetime.now(UTC).timestamp()),
        }
        confirmation_form = ConsentConfirmationForm()
        _populate_authorization_form(confirmation_form, values, "confirmation")
        return render_template(
            "oauth/confirm_login.html",
            client=client,
            form=confirmation_form,
            selected_permissions=[
                OPTIONAL_PERMISSION_DEFINITIONS[scope]["label"] for scope in selected
            ],
        )

    if stage != "confirmation":
        abort(400)
    confirmation_form = ConsentConfirmationForm()
    if not confirmation_form.validate_on_submit():
        abort(400)
    pending = session.get(OAUTH_REVIEW_KEY)
    if (
        not isinstance(pending, dict)
        or pending.get("user_id") != current_user.id
        or pending.get("client_id") != client.client_id
        or pending.get("state") != values["state"]
        or pending.get("values") != values
        or int(pending.get("created_at", 0))
        < int(datetime.now(UTC).timestamp()) - OAUTH_REVIEW_TTL_SECONDS
    ):
        session.pop(OAUTH_REVIEW_KEY, None)
        abort(400)
    selected = [
        scope
        for scope in ordered_optional_scopes(pending.get("selected", []))
        if scope in requested_optional
    ]
    if decision == "change":
        return _permission_view(
            client,
            values,
            requested_optional,
            set(selected),
        )
    if decision != "allow":
        abort(400)
    session.pop(OAUTH_REVIEW_KEY, None)
    save_user_consent(
        current_user.id,
        client.client_id,
        requested_optional,
        selected,
    )
    granted_scope = " ".join(["openid", *selected])
    db.session.flush()
    return _authorization_return(client, values, granted_scope)


def _token_payload(item: OAuthToken, raw_access: str, raw_refresh: str, nonce: str | None):
    now = int(datetime.now(UTC).timestamp())
    user = item.user
    scopes = effective_token_scopes(item.scope, item.user_id, item.client_id)
    item.scope = " ".join(scopes)
    claims = {
        "iss": _issuer(),
        "sub": str(user.id),
        "aud": item.client_id,
        "iat": now,
        "exp": now + current_app.config["ACCESS_TOKEN_TTL"],
        "auth_time": int((user.last_login_at or datetime.now(UTC)).timestamp()),
    }
    if "profile" in scopes:
        claims.update(
            preferred_username=user.username,
            name=user.display_name,
        )
    if "email" in scopes and user.email:
        claims.update(email=user.email, email_verified=bool(user.email_verified))
    if "avatar" in scopes:
        claims["picture"] = _user_picture(user)
    if nonce:
        claims["nonce"] = nonce
    return {
        "access_token": raw_access,
        "refresh_token": raw_refresh,
        "token_type": "Bearer",
        "expires_in": current_app.config["ACCESS_TOKEN_TTL"],
        "scope": " ".join(scopes),
        "id_token": encode_id_token(claims),
    }


@oauth_bp.post("/oauth/token")
@csrf.exempt
def token():
    client = _authenticated_client()
    if client is None:
        return _oauth_error("invalid_client", "客户端认证失败。", 401)
    grant_type = request.form.get("grant_type")
    if grant_type == "authorization_code":
        raw_code = request.form.get("code", "")
        grant = db.session.scalar(
            db.select(AuthorizationGrant).where(
                AuthorizationGrant.code_hash == hash_token(raw_code),
                AuthorizationGrant.client_id == client.client_id,
            )
        )
        if (
            grant is None
            or grant.used_at is not None
            or aware(grant.expires_at) <= datetime.now(UTC)
            or not grant.user.is_active
            or grant.redirect_uri != request.form.get("redirect_uri")
            or not verify_pkce(request.form.get("code_verifier", ""), grant.code_challenge)
        ):
            return _oauth_error("invalid_grant", "授权码不可用。")
        grant.used_at = datetime.now(UTC)
        raw_access, raw_refresh = new_token(32), new_token(40)
        item = OAuthToken(
            client_id=client.client_id,
            user_id=grant.user_id,
            access_token_hash=hash_token(raw_access),
            refresh_token_hash=hash_token(raw_refresh),
            scope=grant.scope,
            expires_at=expires_in(current_app.config["ACCESS_TOKEN_TTL"]),
            refresh_expires_at=expires_in(current_app.config["REFRESH_TOKEN_TTL"]),
        )
        db.session.add(item)
        db.session.commit()
        return jsonify(_token_payload(item, raw_access, raw_refresh, grant.nonce))
    if grant_type == "refresh_token":
        raw = request.form.get("refresh_token", "")
        old = db.session.scalar(
            db.select(OAuthToken).where(
                OAuthToken.refresh_token_hash == hash_token(raw),
                OAuthToken.client_id == client.client_id,
            )
        )
        if (
            old is None
            or old.revoked_at is not None
            or aware(old.refresh_expires_at) <= datetime.now(UTC)
            or not old.user.is_active
        ):
            return _oauth_error("invalid_grant", "刷新令牌不可用。")
        old.revoked_at = datetime.now(UTC)
        raw_access, raw_refresh = new_token(32), new_token(40)
        item = OAuthToken(
            client_id=old.client_id,
            user_id=old.user_id,
            access_token_hash=hash_token(raw_access),
            refresh_token_hash=hash_token(raw_refresh),
            scope=" ".join(
                effective_token_scopes(old.scope, old.user_id, old.client_id)
            ),
            expires_at=expires_in(current_app.config["ACCESS_TOKEN_TTL"]),
            refresh_expires_at=expires_in(current_app.config["REFRESH_TOKEN_TTL"]),
        )
        db.session.add(item)
        db.session.commit()
        return jsonify(_token_payload(item, raw_access, raw_refresh, None))
    return _oauth_error("unsupported_grant_type", "不支持这个授权类型。")


def _bearer_token() -> OAuthToken | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    item = db.session.scalar(
        db.select(OAuthToken).where(OAuthToken.access_token_hash == hash_token(header[7:].strip()))
    )
    if (
        item is None
        or item.revoked_at is not None
        or aware(item.expires_at) <= datetime.now(UTC)
        or not item.user.is_active
        or _client(item.client_id) is None
    ):
        return None
    return item


@oauth_bp.get("/oauth/userinfo")
def userinfo():
    item = _bearer_token()
    if item is None:
        return _oauth_error("invalid_token", "访问令牌不可用。", 401)
    user = item.user
    scopes = effective_token_scopes(item.scope, item.user_id, item.client_id)
    payload = {"sub": str(user.id)}
    if "profile" in scopes:
        payload.update(preferred_username=user.username, name=user.display_name)
    if "email" in scopes and user.email:
        payload.update(email=user.email, email_verified=bool(user.email_verified))
    if "avatar" in scopes:
        payload["picture"] = _user_picture(user)
    return jsonify(payload)


@oauth_bp.post("/oauth/revoke")
@csrf.exempt
def revoke():
    client = _authenticated_client()
    if client is None:
        return _oauth_error("invalid_client", "客户端认证失败。", 401)
    raw = request.form.get("token", "")
    digest = hash_token(raw)
    item = db.session.scalar(
        db.select(OAuthToken).where(
            OAuthToken.client_id == client.client_id,
            db.or_(
                OAuthToken.access_token_hash == digest,
                OAuthToken.refresh_token_hash == digest,
            ),
        )
    )
    if item:
        item.revoked_at = datetime.now(UTC)
        db.session.commit()
    return "", 200


@oauth_bp.post("/oauth/introspect")
@csrf.exempt
def introspect():
    client = _authenticated_client()
    if client is None:
        return _oauth_error("invalid_client", "客户端认证失败。", 401)
    raw = request.form.get("token", "")
    digest = hash_token(raw)
    item = db.session.scalar(
        db.select(OAuthToken).where(
            OAuthToken.client_id == client.client_id,
            db.or_(
                OAuthToken.access_token_hash == digest,
                OAuthToken.refresh_token_hash == digest,
            ),
        )
    )
    if (
        item is None
        or item.revoked_at is not None
        or not item.user.is_active
        or _client(item.client_id) is None
    ):
        return jsonify(active=False)
    is_access = item.access_token_hash == digest
    expiry = item.expires_at if is_access else item.refresh_expires_at
    if aware(expiry) <= datetime.now(UTC):
        return jsonify(active=False)
    scopes = effective_token_scopes(item.scope, item.user_id, item.client_id)
    payload = {
        "active": True,
        "client_id": item.client_id,
        "sub": str(item.user_id),
        "scope": " ".join(scopes),
        "token_type": "access_token" if is_access else "refresh_token",
        "exp": int(aware(expiry).timestamp()),
    }
    user = item.user
    if "email" in scopes and user.email:
        payload["email"] = user.email
        payload["email_verified"] = bool(user.email_verified)
    return jsonify(payload)
