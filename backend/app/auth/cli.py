import click
from flask.cli import with_appcontext
from sqlalchemy import text

from ..extensions import db
from ..models import AuthRate, AuthSession, AuthSettings, EmailChallenge, SiteSettings, User
from . import mail, sessions
from .security import AuthError, email, now, password, username


def new_password():
    value = click.prompt(
        "新密码（至少12个字符）", hide_input=True, confirmation_prompt="再次输入密码"
    )
    try:
        return password(value, value)
    except AuthError as error:
        raise click.ClickException(error.message) from None


@click.command("create-admin")
@click.option("--username", "name", required=True)
@click.option("--email", "address", required=True)
@with_appcontext
def create_admin(name, address):
    """Create the first administrator from a trusted server terminal only."""
    try:
        name = username(name)
        address = email(address)
    except AuthError as error:
        raise click.ClickException(error.message) from None
    hashed = new_password()
    db.session.execute(text("SELECT pg_advisory_xact_lock(782341)"))
    if db.session.execute(db.select(User.id).where(User.role == "admin")).scalar():
        raise click.ClickException("管理员已存在；初始化未修改任何账号。")
    if db.session.execute(
        db.select(User.id).where((User.username == name) | (User.email == address))
    ).scalar():
        raise click.ClickException("账号名或邮箱已使用。")
    db.session.add(
        User(username=name, nickname=name, email=address, password_hash=hashed, role="admin")
    )
    db.session.commit()
    click.echo("首位管理员已创建。请确保指定邮箱由你本人控制。")


@click.command("reset-password")
@click.option("--username", "name", required=True)
@with_appcontext
def reset_password(name):
    """Server operator recovery; revokes every old login session."""
    user = db.session.execute(
        db.select(User).where(User.username == name.lower()).with_for_update()
    ).scalar_one_or_none()
    if not user:
        raise click.ClickException("未找到账号。")
    user.password_hash = new_password()
    sessions.revoke_user(user)
    db.session.commit()
    click.echo("密码已重设，旧登录会话已撤销。")


@click.command("configure-mail")
@click.option("--host", required=True)
@click.option("--port", type=int, required=True)
@click.option("--sender", required=True)
@click.option("--security", type=click.Choice(["starttls", "tls", "plain"]), default="starttls")
@click.option("--username", "smtp_user", default="")
@with_appcontext
def configure_mail(host, port, sender, security, smtp_user):
    """Probe and encrypt SMTP configuration; password is never a CLI argument."""
    try:
        sender = email(sender)
        secret = click.prompt("SMTP密码", hide_input=True) if smtp_user else ""
        mail.save_configuration(
            {
                "host": host,
                "port": port,
                "sender": sender,
                "security": security,
                "username": smtp_user,
                "password": secret,
            }
        )
    except (AuthError, ValueError, OSError):
        db.session.rollback()
        raise click.ClickException("邮件配置或连接验证未通过；没有保存新配置。") from None
    click.echo("邮件连接已验证，配置已加密保存。")


@click.command("mail-test")
@click.option("--recipient", required=True)
@with_appcontext
def test_mail(recipient):
    try:
        mail.send(email(recipient))
    except AuthError as error:
        raise click.ClickException(error.message) from None
    click.echo("测试邮件已提交邮件服务器。")


@click.command("registration")
@click.argument("state", type=click.Choice(["on", "off"]))
@with_appcontext
def registration(state):
    db.session.execute(text("SELECT pg_advisory_xact_lock(782341)"))
    site = db.session.get(SiteSettings, 1)
    if site:
        site.version += 1
    row = db.session.get(AuthSettings, 1)
    if state == "on":
        has_admin = db.session.execute(
            db.select(User.id).where(User.role == "admin", User.is_active.is_(True))
        ).scalar()
        if not has_admin or not mail.configuration():
            raise click.ClickException("请先创建管理员并配置邮件。")
    row.registration_open = state == "on"
    db.session.commit()
    click.echo("注册已开启。" if state == "on" else "注册已关闭。")


@click.command("auth-cleanup")
@with_appcontext
def cleanup():
    timestamp = now()
    db.session.execute(
        db.delete(EmailChallenge).where(
            (EmailChallenge.expires_at < timestamp) | (EmailChallenge.consumed_at.is_not(None))
        )
    )
    db.session.execute(
        db.delete(AuthSession).where(
            (AuthSession.expires_at < timestamp) | (AuthSession.revoked_at.is_not(None))
        )
    )
    db.session.execute(db.delete(AuthRate).where(AuthRate.expires_at < timestamp))
    db.session.commit()
    click.echo("过期验证、会话和限流记录已清理；用户账号未改变。")


def register(app):
    for command in [create_admin, reset_password, configure_mail, test_mail, registration, cleanup]:
        app.cli.add_command(command)
