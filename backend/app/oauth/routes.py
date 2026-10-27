import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from authlib.oauth2 import OAuth2Error
from authlib.oidc.core.errors import ConsentRequiredError, LoginRequiredError
from flask import Blueprint, current_app, g, jsonify, redirect, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..auth import sessions
from ..auth.routes import csrf
from ..auth.security import AuthError, decrypt, encrypt, limit, now, require_json
from ..extensions import db
from ..responses import success
from .keys import private_key
from .models import OAuthClient, OAuthConsent, OAuthTransaction
from .requests import CanonicalRequest
from .service import SCOPES, claims, consent_for, transaction

bp = Blueprint("oauth", __name__)


def server():
    return current_app.extensions["bg_oauth"]


def protocol_error(code="invalid_request", status=400):
    return jsonify(error=code, error_description="请求无法完成，请从应用重新开始。"), status


def oauth_request(parameters):
    return CanonicalRequest(
        "GET",
        current_app.config["BG_PUBLIC_URL"].rstrip("/")
        + "/oauth/authorize?"
        + urlencode(parameters),
    )


def check_parameters(parameters):
    allowed = {
        "client_id",
        "redirect_uri",
        "response_type",
        "response_mode",
        "scope",
        "state",
        "nonce",
        "code_challenge",
        "code_challenge_method",
        "prompt",
        "max_age",
        "acr_values",
    }
    if set(parameters) - allowed:
        raise AuthError("invalid_request", "不支持此登录请求中的扩展参数。")
    if parameters.get("response_mode", "query") != "query":
        raise AuthError("invalid_request", "仅支持query返回模式。")
    if (
        parameters.get("response_type") != "code"
        or not parameters.get("redirect_uri")
        or "openid" not in parameters.get("scope", "").split()
    ):
        raise AuthError("invalid_request", "应用登录请求不完整。")
    if not 1 <= len(parameters.get("state", "")) <= 512 or len(parameters.get("nonce", "")) > 256:
        raise AuthError("invalid_request", "应用登录状态参数不可用。")
    if (
        not re.fullmatch(r"[A-Za-z0-9_-]{43}", parameters.get("code_challenge", ""))
        or parameters.get("code_challenge_method") != "S256"
    ):
        raise AuthError("invalid_request", "应用必须使用S256 PKCE。")
    prompts = parameters.get("prompt", "").split()
    if set(prompts) - {"none", "login", "consent", "select_account"} or (
        "none" in prompts and len(prompts) != 1
    ):
        raise AuthError("invalid_request", "登录提示参数不可用。")
    if "max_age" in parameters and not re.fullmatch(r"[0-9]{1,8}", parameters["max_age"]):
        raise AuthError("invalid_request", "登录有效期参数不可用。")


def validated(parameters, user):
    check_parameters(parameters)
    return server().get_consent_grant(oauth_request(parameters), end_user=user)


def issue(parameters, browser, selected, approve=True, explicit=False):
    # Validate the original request again before scope selection; all external
    # redirect material is immutable, encrypted server-side transaction data.
    grant = validated(parameters, browser.user)
    client = grant.request.client
    client = db.session.scalar(
        db.select(OAuthClient)
        .where(OAuthClient.id == client.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not client.active:
        raise AuthError("authorization_expired", "应用已停用。")
    grant = validated(parameters, browser.user)
    if approve:
        requested = set(parameters["scope"].split())
        if (
            not isinstance(selected, list)
            or not all(isinstance(s, str) for s in selected)
            or "openid" not in selected
            or not set(selected) <= requested
        ):
            raise AuthError("invalid_request", "分享范围不可用。")
        row = consent_for(browser.user_id, client.id)
        if not row:
            row = OAuthConsent(
                user_id=browser.user_id, client_id=client.id, scopes=" ".join(sorted(set(selected)))
            )
            db.session.add(row)
        elif row.revoked_at:
            row.revoked_at = None
            row.scopes = " ".join(sorted(set(selected)))
        elif explicit and set(row.scopes.split()) != set(selected):
            from .service import revoke_connection

            revoke_connection(row)
            row.revoked_at = None
            row.scopes = " ".join(sorted(set(selected)))
        row.last_used_at = now()
        db.session.flush()
        g.oauth_consent = row
        narrowed = dict(parameters, scope=" ".join(sorted(set(selected))))
        req = oauth_request(narrowed)
        grant = server().get_consent_grant(req, end_user=browser.user)
    else:
        req = oauth_request(parameters)
    return server().create_authorization_response(
        req, grant_user=browser.user if approve else None, grant=grant
    )


@bp.get("/.well-known/openid-configuration")
def discovery():
    issuer = current_app.config["BG_PUBLIC_URL"].rstrip("/")
    return jsonify(
        issuer=issuer,
        authorization_endpoint=issuer + "/oauth/authorize",
        token_endpoint=issuer + "/oauth/token",
        userinfo_endpoint=issuer + "/oauth/userinfo",
        jwks_uri=issuer + "/oauth/jwks",
        revocation_endpoint=issuer + "/oauth/revoke",
        introspection_endpoint=issuer + "/oauth/introspect",
        response_types_supported=["code"],
        response_modes_supported=["query"],
        grant_types_supported=["authorization_code", "refresh_token"],
        subject_types_supported=["public"],
        id_token_signing_alg_values_supported=["RS256"],
        token_endpoint_auth_methods_supported=["client_secret_basic"],
        scopes_supported=sorted(SCOPES),
        claims_supported=[
            "sub",
            "name",
            "nickname",
            "preferred_username",
            "picture",
            "email",
            "email_verified",
            "iss",
            "aud",
            "exp",
            "iat",
            "auth_time",
            "nonce",
        ],
        code_challenge_methods_supported=["S256"],
        claims_parameter_supported=False,
        request_parameter_supported=False,
        request_uri_parameter_supported=False,
    )


@bp.get("/oauth/jwks")
def jwks():
    return jsonify(keys=[private_key().as_dict(private=False)])


@bp.get("/oauth/authorize")
def authorize():
    try:
        if any(len(request.args.getlist(key)) != 1 for key in request.args):
            return protocol_error()
        limit("oauth-authorize", maximum=120)
        parameters = request.args.to_dict()
        browser = sessions.load(lock=True) or sessions.rotate()
        g.auth_session = browser
        grant = validated(parameters, browser.user)
        consent = consent_for(browser.user_id, grant.request.client.id) if browser.user_id else None
        prompts = parameters.get("prompt", "").split()
        old = browser.user_id and (
            "max_age" in parameters
            and (now() - browser.created_at).total_seconds() >= int(parameters["max_age"])
        )
        force = "login" in prompts or "select_account" in prompts or old
        approved = bool(
            consent
            and not consent.revoked_at
            and set(parameters["scope"].split()) <= set(consent.scopes.split())
        )
        if "none" in prompts:
            if force or not browser.user_id:
                return server().handle_error_response(
                    grant.request,
                    LoginRequiredError(
                        redirect_uri=parameters["redirect_uri"], state=parameters["state"]
                    ),
                )
            if not approved:
                return server().handle_error_response(
                    grant.request,
                    ConsentRequiredError(
                        redirect_uri=parameters["redirect_uri"], state=parameters["state"]
                    ),
                )
        if browser.user_id and not force and approved and "consent" not in prompts:
            response = issue(parameters, browser, parameters["scope"].split())
            db.session.commit()
            return response
        if force:
            browser = sessions.rotate()
        reference = secrets.token_urlsafe(24)
        db.session.add(
            OAuthTransaction(
                id=reference,
                browser_key=browser.browser_key,
                user_id=browser.user_id,
                encrypted_data=encrypt(parameters, "oauth-transaction"),
                expires_at=now() + timedelta(minutes=15),
            )
        )
        db.session.commit()
        target = "/authorize?" + urlencode({"tx": reference})
        return redirect(target if browser.user_id else "/login?" + urlencode({"next": target}))
    except OAuth2Error as error:
        db.session.rollback()
        return server().handle_error_response(oauth_request(parameters), error)
    except AuthError as error:
        db.session.rollback()
        return protocol_error("invalid_request", error.status)


def consent_transaction(value):
    browser = sessions.load(lock=True)
    if not browser or not browser.user_id:
        raise AuthError("authentication_required", "请先登录后继续。", 401)
    g.auth_session = browser
    row = (
        db.session.scalar(
            db.select(OAuthTransaction).where(OAuthTransaction.id == value).with_for_update()
        )
        if isinstance(value, str) and len(value) <= 64
        else None
    )
    transaction(row, browser)
    if not row.user_id:
        row.user_id = browser.user_id
    return row, browser, decrypt(row.encrypted_data, "oauth-transaction")


@bp.get("/api/oauth/consent")
def consent_info():
    row, browser, parameters = consent_transaction(request.args.get("tx"))
    try:
        grant = validated(parameters, browser.user)
    except OAuth2Error:
        raise AuthError("authorization_expired", "应用登录请求已失效，请回到应用重试。") from None
    client = grant.request.client
    db.session.commit()
    return success(
        {
            "application": {
                "name": client.name,
                "iconUrl": f"/api/apps/{client.id}/icon/{client.icon_key}"
                if client.icon_key
                else None,
                "description": client.description,
                "homepage": client.homepage,
                "privacyUrl": client.privacy_url,
                "termsUrl": client.terms_url,
                "returnHost": urlsplit(parameters["redirect_uri"]).netloc,
            },
            "scopes": parameters["scope"].split(),
            "user": {"nickname": browser.user.nickname, "username": browser.user.username},
            "expiresAt": row.expires_at.isoformat(),
        }
    )


@bp.post("/api/oauth/consent")
def consent_submit():
    try:
        csrf()
        data = require_json()
        row, browser, parameters = consent_transaction(data.get("tx"))
        if not isinstance(data.get("approve"), bool):
            raise AuthError("invalid_request", "请选择是否继续。")
        response = issue(
            parameters, browser, data.get("scopes", []), data["approve"], explicit=True
        )
        if response.status_code not in {302, 303}:
            raise AuthError("authorization_expired", "应用登录请求已失效，请重新开始。")
        row.consumed_at = now()
        location = response.headers["Location"]
        db.session.commit()
        return success({"redirectTo": location})
    except OAuth2Error:
        db.session.rollback()
        raise AuthError("authorization_expired", "应用登录请求不可用，请回到应用重试。") from None
    except IntegrityError:
        db.session.rollback()
        raise AuthError("authorization_expired", "登录请求已经使用，请从应用重新开始。") from None


def protocol_operation(operation):
    try:
        if (
            request.args
            or request.mimetype != "application/x-www-form-urlencoded"
            or any(len(request.form.getlist(k)) != 1 for k in request.form)
            or "client_secret" in request.form
        ):
            return protocol_error()
        limit("oauth-credentials", maximum=180)
        response = operation()
        if response.status_code < 400 or getattr(g, "oauth_persist", False):
            db.session.commit()
        else:
            db.session.rollback()
        return response
    except OAuth2Error as error:
        db.session.rollback()
        return protocol_error(error.error, error.status_code)
    except SQLAlchemyError:
        db.session.rollback()
        return protocol_error("temporarily_unavailable", 503)
    except AuthError as error:
        db.session.rollback()
        return protocol_error("temporarily_unavailable", error.status)


@bp.post("/oauth/token")
def token():
    return protocol_operation(lambda: server().create_token_response())


@bp.post("/oauth/revoke")
def revoke():
    return protocol_operation(lambda: server().create_endpoint_response("revocation"))


@bp.post("/oauth/introspect")
def introspect():
    return protocol_operation(lambda: server().create_endpoint_response("introspection"))


@bp.get("/oauth/userinfo")
def userinfo():
    resource = current_app.extensions["bg_resource"]
    try:
        credential = resource.acquire_token("openid")
        result = claims(credential.get_user(), credential.scope)
        db.session.commit()
        return jsonify(result)
    except OAuth2Error as error:
        db.session.rollback()
        return server().handle_response(
            error.status_code, dict(error.get_body()), error.get_headers()
        )


@bp.get("/oauth/picture")
def picture():
    from flask import send_file

    from ..account import avatars

    try:
        credential = current_app.extensions["bg_resource"].acquire_token("profile")
        user = credential.get_user()
        key = user.avatar_key
        if not key or not avatars.KEY.fullmatch(key):
            return protocol_error("not_found", 404)
        path = avatars.directory() / key
        if not path.is_file() or path.is_symlink():
            return protocol_error("not_found", 404)
        db.session.commit()
        return send_file(path, mimetype="image/png", conditional=False, etag=False, max_age=0)
    except OAuth2Error as error:
        db.session.rollback()
        return server().handle_response(
            error.status_code, dict(error.get_body()), error.get_headers()
        )
