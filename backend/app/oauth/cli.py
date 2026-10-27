import json
import os
import secrets
from datetime import timedelta
from pathlib import Path

import click
from flask.cli import with_appcontext

from ..auth.security import digest, now
from ..extensions import db
from .models import OAuthClient, OAuthCode, OAuthToken, OAuthTransaction
from .service import SCOPES, web_url


def credential_file(path, client, secret):
    destination = Path(path)
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"client_id": client.id, "client_secret": secret}, stream)


@click.command("oauth-client-create")
@click.option("--name", required=True)
@click.option("--redirect-uri", "redirects", multiple=True, required=True)
@click.option("--scope", default="openid profile email")
@click.option("--description", default="")
@click.option("--homepage", default="")
@click.option("--privacy-url", default="")
@click.option("--terms-url", default="")
@click.option("--credentials-file", required=True)
@with_appcontext
def create(name, redirects, scope, description, homepage, privacy_url, terms_url, credentials_file):
    try:
        if (
            not 1 <= len(name.strip()) <= 80
            or len(description) > 240
            or not set(scope.split()) <= SCOPES
            or "openid" not in scope.split()
        ):
            raise ValueError()
        redirects = [web_url(value) for value in redirects]
        homepage = web_url(homepage, optional=True)
        privacy_url = web_url(privacy_url, optional=True)
        terms_url = web_url(terms_url, optional=True)
        secret = secrets.token_urlsafe(48)
        row = OAuthClient(
            id=secrets.token_urlsafe(24),
            secret_digest=digest(secret),
            name=name.strip(),
            description=description,
            redirect_uris=redirects,
            scopes=" ".join(sorted(set(scope.split()))),
            homepage=homepage,
            privacy_url=privacy_url,
            terms_url=terms_url,
        )
        credential_file(credentials_file, row, secret)
        db.session.add(row)
        db.session.commit()
    except (ValueError, OSError):
        db.session.rollback()
        raise click.ClickException("应用资料或凭据文件不可用；不覆盖已有文件。") from None
    click.echo("应用已登记；凭据仅保存在指定的新0600文件，未输出密钥。")


@click.command("oauth-client-list")
@with_appcontext
def list_clients():
    for row in db.session.scalars(db.select(OAuthClient).order_by(OAuthClient.created_at)):
        click.echo(f"{row.id}  {row.name}  {'enabled' if row.active else 'disabled'}")


def invalidate(client):
    client.version += 1
    for model in [OAuthCode, OAuthToken]:
        db.session.execute(
            db.update(model)
            .where(model.client_id == client.id, model.revoked_at.is_(None))
            .values(revoked_at=now())
        )


@click.command("oauth-client-state")
@click.argument("client_id")
@click.argument("state", type=click.Choice(["on", "off"]))
@with_appcontext
def state(client_id, state):
    row = db.session.scalar(
        db.select(OAuthClient).where(OAuthClient.id == client_id).with_for_update()
    )
    if not row:
        raise click.ClickException("应用不存在。")
    if row.active != (state == "on"):
        invalidate(row)
        row.active = state == "on"
    db.session.commit()
    click.echo("应用状态已更新。")


@click.command("oauth-client-rotate")
@click.argument("client_id")
@click.option("--credentials-file", required=True)
@with_appcontext
def rotate(client_id, credentials_file):
    row = db.session.scalar(
        db.select(OAuthClient).where(OAuthClient.id == client_id).with_for_update()
    )
    if not row:
        raise click.ClickException("应用不存在。")
    value = secrets.token_urlsafe(48)
    try:
        credential_file(credentials_file, row, value)
    except OSError:
        raise click.ClickException("不能创建新凭据文件，不覆盖已有文件。") from None
    row.secret_digest = digest(value)
    invalidate(row)
    db.session.commit()
    click.echo("密钥已轮换并撤销旧应用凭据；新密钥仅保存在指定文件。")


@click.command("oauth-cleanup")
@with_appcontext
def cleanup():
    db.session.execute(
        db.delete(OAuthTransaction).where(
            (OAuthTransaction.expires_at < now()) | OAuthTransaction.consumed_at.is_not(None)
        )
    )
    # Retain code and refresh tombstones for replay detection over their lifetime.
    db.session.execute(
        db.delete(OAuthCode).where(OAuthCode.expires_at < now() - timedelta(days=30))
    )
    db.session.execute(db.delete(OAuthToken).where(OAuthToken.refresh_expires_at < now()))
    db.session.commit()
    click.echo("过期授权事务和凭据已清理；保留有效期内的重放检测记录。")


def register(app):
    for command in [create, list_clients, state, rotate, cleanup]:
        app.cli.add_command(command)
