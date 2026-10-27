import json
import os
import secrets
from pathlib import Path

import click
from flask import current_app
from flask.cli import with_appcontext
from joserfc.jwk import RSAKey


def private_key():
    data = json.loads((Path(current_app.config["BG_SIGNING_KEY_DIR"]) / "oidc.json").read_text())
    key = RSAKey.import_key(data)
    if not key.is_private:
        raise ValueError("Private signing key required")
    return key


@click.command("oauth-keys-init")
@with_appcontext
def initialize():
    directory = Path(current_app.config["BG_SIGNING_KEY_DIR"])
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / "oidc.json"
    if path.exists():
        private_key()
        click.echo("已有签名密钥保持不变。")
        return
    key = RSAKey.generate_key(
        2048, parameters={"kid": secrets.token_urlsafe(16), "use": "sig", "alg": "RS256"}
    )
    temporary = directory / (".key-" + secrets.token_hex(8))
    try:
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(key.as_dict(private=True), stream)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            private_key()
    finally:
        temporary.unlink(missing_ok=True)
    click.echo("签名密钥已就绪；未输出密钥内容。")
