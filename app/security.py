from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from datetime import UTC, datetime, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from flask import abort, current_app, request
from flask_login import current_user


def new_token(size: int = 32) -> str:
    return secrets.token_urlsafe(size)


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def request_fingerprint(scope: str) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    address = forwarded.split(",", 1)[0].strip() if forwarded else (request.remote_addr or "")
    material = f"{scope}|{address}|{request.user_agent.string[:200]}".encode()
    return hmac.new(current_app.secret_key.encode(), material, hashlib.sha256).hexdigest()


def request_client_ip_digest() -> str:
    """Keyed digest of the client address only, used to detect new networks."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    address = forwarded.split(",", 1)[0].strip() if forwarded else (request.remote_addr or "")
    material = f"client-ip|{address}".encode()
    return hmac.new(current_app.secret_key.encode(), material, hashlib.sha256).hexdigest()


def is_safe_local_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlsplit(value)
    return (
        not parsed.scheme
        and not parsed.netloc
        and value.startswith("/")
        and not value.startswith("//")
    )


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.has_permission("admin.access"):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def verify_pkce(verifier: str, challenge: str) -> bool:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    return hmac.compare_digest(encoded.decode(), challenge)


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _totp_value(secret: str, counter: int) -> str:
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{number:06d}"


def verify_totp(secret: str, code: str, *, at_time: int | None = None) -> bool:
    now = int(at_time or time.time())
    clean = "".join(character for character in code if character.isdigit())
    return len(clean) == 6 and any(
        hmac.compare_digest(_totp_value(secret, now // 30 + offset), clean) for offset in (-1, 0, 1)
    )


def ensure_signing_keys(instance_path: str) -> tuple[Path, Path]:
    key_dir = Path(instance_path) / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    private_path = key_dir / "oidc-private.pem"
    public_path = key_dir / "oidc-public.pem"
    if not private_path.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        public_path.write_bytes(
            key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
    return private_path, public_path


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def encode_id_token(claims: dict) -> str:
    header = {"alg": "RS256", "typ": "JWT", "kid": "cloudgate-rs256-1"}
    parts = [
        _b64(json.dumps(header, separators=(",", ":")).encode()),
        _b64(json.dumps(claims, separators=(",", ":"), ensure_ascii=False).encode()),
    ]
    signing_input = ".".join(parts).encode()
    key = serialization.load_pem_private_key(
        Path(current_app.config["OIDC_PRIVATE_KEY"]).read_bytes(), password=None
    )
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return ".".join([*parts, _b64(signature)])


def public_jwk() -> dict:
    key = serialization.load_pem_public_key(
        Path(current_app.config["OIDC_PUBLIC_KEY"]).read_bytes()
    )
    numbers = key.public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": "cloudgate-rs256-1",
        "n": _b64(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
        "e": _b64(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
    }


def expires_in(seconds: int) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=seconds)
