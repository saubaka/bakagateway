import base64
import binascii
import io
import re
import secrets
import time
import warnings
from pathlib import Path

import click
from flask import current_app
from flask.cli import with_appcontext
from PIL import Image, ImageOps, UnidentifiedImageError

from ..auth.security import AuthError
from ..extensions import db
from ..models import User

Image.MAX_IMAGE_PIXELS = 16_000_000
KEY = re.compile(r"[a-f0-9]{32}\.png")


def directory():
    return Path(current_app.config["BG_UPLOAD_DIR"])


def save(value):
    if not isinstance(value, str) or len(value) > 2_796_204:
        raise AuthError("request_too_large", "头像文件不能超过2MiB。", 413)
    try:
        content = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise AuthError("invalid_image", "请选择有效的PNG、JPEG或静态WebP图片。") from None
    if len(content) > 2 * 1024 * 1024:
        raise AuthError("request_too_large", "头像文件不能超过2MiB。", 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content), formats=["PNG", "JPEG", "WEBP"]) as source:
                if (
                    max(source.size) > 4096
                    or source.width * source.height > 16_000_000
                    or getattr(source, "n_frames", 1) != 1
                ):
                    raise ValueError("Image dimensions or animation rejected")
                source.load()
                crop = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGBA"), (256, 256))
                clean = Image.new("RGBA", (256, 256))
                clean.paste(crop)
                output = io.BytesIO()
                clean.save(output, format="PNG")
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise AuthError(
            "invalid_image", "图片不可用，请使用4096像素以内的PNG、JPEG或静态WebP。"
        ) from None
    key = secrets.token_hex(16) + ".png"
    path = directory() / key
    try:
        directory().mkdir(parents=True, exist_ok=True, mode=0o750)
        with path.open("xb") as stream:
            stream.write(output.getvalue())
        path.chmod(0o640)
    except OSError:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise AuthError("storage_unavailable", "头像暂时无法保存，请稍后重试。", 503) from None
    return key


@click.command("avatar-cleanup")
@with_appcontext
def cleanup_command():
    """Remove unreferenced generated avatars older than one hour."""
    referenced = set(
        db.session.scalars(db.select(User.avatar_key).where(User.avatar_key.is_not(None)))
    )
    from ..oauth.models import OAuthClient

    referenced.update(
        db.session.scalars(db.select(OAuthClient.icon_key).where(OAuthClient.icon_key.is_not(None)))
    )
    count = 0
    for path in directory().glob("*.png"):
        if (
            KEY.fullmatch(path.name)
            and path.name not in referenced
            and not path.is_symlink()
            and path.stat().st_mtime < time.time() - 3600
        ):
            path.unlink()
            count += 1
    click.echo(f"已清理{count}个未引用头像；当前头像保持不变。")
