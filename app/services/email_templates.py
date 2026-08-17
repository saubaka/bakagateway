from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from html import escape
from html.parser import HTMLParser
from types import SimpleNamespace
from urllib.parse import urlsplit

from flask import current_app

from app.extensions import db
from app.models import MailTemplate


@dataclass(frozen=True)
class MailTemplateVariable:
    name: str
    label: str
    sample: str
    required: bool = False


@dataclass(frozen=True)
class MailTemplateDefinition:
    key: str
    name: str
    description: str
    subject: str
    body_html: str
    variables: tuple[MailTemplateVariable, ...]


PLACEHOLDER = re.compile(r"{{\s*([A-Za-z0-9_]+)\s*}}")
ALLOWED_TAGS = frozenset(
    {
        "a",
        "blockquote",
        "br",
        "code",
        "div",
        "em",
        "h1",
        "h2",
        "h3",
        "li",
        "ol",
        "p",
        "pre",
        "span",
        "strong",
        "u",
        "s",
        "ul",
    }
)
VOID_TAGS = frozenset({"br"})
BLOCKED_TAGS = frozenset(
    {
        "script",
        "style",
        "iframe",
        "object",
        "embed",
        "link",
        "meta",
        "form",
        "input",
        "button",
        "svg",
        "math",
    }
)
ALLOWED_STYLE_PROPERTIES = frozenset(
    {
        "background-color",
        "border-radius",
        "color",
        "font-size",
        "font-style",
        "font-weight",
        "line-height",
        "margin",
        "padding",
        "text-align",
        "text-decoration",
    }
)
UNSAFE_STYLE_CONTENT = re.compile(r"(?:url\s*\(|expression|javascript|@import|<|>)", re.I)
UNSAFE_HTML_CONTENT = re.compile(
    r"<\s*(?:script|style|iframe|object|embed|link|meta|form|input|button|svg|math)\b"
    r"|javascript:|expression\s*\(|url\s*\(",
    re.I,
)


def _verification_variables() -> tuple[MailTemplateVariable, ...]:
    return (
        MailTemplateVariable("app_name", "应用名称", "baka网关"),
        MailTemplateVariable("action", "操作说明", "验证baka网关账号的当前邮箱"),
        MailTemplateVariable("code", "六位验证码", "123456", required=True),
        MailTemplateVariable("ttl_minutes", "有效分钟数", "10", required=True),
        MailTemplateVariable("recipient_email", "收件邮箱", "name@example.com"),
        MailTemplateVariable("issuer", "发行者地址", "http://127.0.0.1:5100"),
        MailTemplateVariable("support_email", "支持邮箱", "support@example.com"),
        MailTemplateVariable("current_year", "当前年份", "2026"),
    )


def _code_html(action: str) -> str:
    return (
        "<h1>{{ app_name }}</h1>"
        f"<p>你正在{action}。</p>"
        "<p>验证码：<strong>{{ code }}</strong></p>"
        "<p>有效时间：{{ ttl_minutes }} 分钟</p>"
        "<p>如果不是你本人操作，请忽略这封邮件。不要把验证码提供给其他人。</p>"
        "<p>这封邮件发送至 {{ recipient_email }}。</p>"
    )


MAIL_TEMPLATE_DEFINITIONS: tuple[MailTemplateDefinition, ...] = (
    MailTemplateDefinition(
        key="smtp_test",
        name="SMTP 连接测试邮件",
        description="管理员在邮件服务页发送固定测试邮件时使用。",
        subject="{{ app_name }}邮件服务测试",
        body_html=(
            "<h1>{{ app_name }}邮件服务测试</h1>"
            "<p>这是一封由baka网关管理员后台发送的测试邮件。</p>"
            "<p>如果你看到这封邮件，说明当前SMTP连接可以正常发送邮件。</p>"
            "<p>测试时间：{{ tested_at }}</p>"
        ),
        variables=(
            MailTemplateVariable("app_name", "应用名称", "baka网关"),
            MailTemplateVariable("tested_at", "测试时间", "2026-08-15 16:43"),
            MailTemplateVariable("provider_name", "连接名称", "主要邮件服务"),
        ),
    ),
    MailTemplateDefinition(
        key="admin_email_verification",
        name="管理员邮箱验证码",
        description="管理员在验证策略页验证自身邮箱并解锁公开邮件策略时使用。",
        subject="{{ app_name }}管理员邮箱验证码",
        body_html=_code_html("验证baka网关管理员邮箱"),
        variables=_verification_variables(),
    ),
    MailTemplateDefinition(
        key="registration",
        name="新账号注册验证码",
        description="公开注册开启后，新用户先验证邮箱再创建正式账号。",
        subject="{{ app_name }}注册邮箱验证码",
        body_html=_code_html("创建baka网关账号"),
        variables=_verification_variables(),
    ),
    MailTemplateDefinition(
        key="account_email_verification",
        name="已有邮箱验证验证码",
        description="已有账号在个人资料页验证当前绑定邮箱时使用。",
        subject="{{ app_name }}账号邮箱验证码",
        body_html=_code_html("验证baka网关账号的当前邮箱"),
        variables=_verification_variables(),
    ),
    MailTemplateDefinition(
        key="change_email",
        name="更换邮箱验证码",
        description="已登录用户把账号邮箱更换为新邮箱前，先验证新邮箱。",
        subject="{{ app_name }}更换邮箱验证码",
        body_html=_code_html("更换baka网关账号邮箱"),
        variables=_verification_variables(),
    ),
    MailTemplateDefinition(
        key="password_reset",
        name="找回密码验证码",
        description="用户通过绑定邮箱验证身份后继续设置新密码。",
        subject="{{ app_name }}找回密码验证码",
        body_html=_code_html("找回baka网关账号密码"),
        variables=_verification_variables(),
    ),
)
MAIL_TEMPLATE_DEFINITION_MAP = {item.key: item for item in MAIL_TEMPLATE_DEFINITIONS}
MAIL_TEMPLATE_KEYS = frozenset(MAIL_TEMPLATE_DEFINITION_MAP)


class _EmailHTMLSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in BLOCKED_TAGS:
            self._blocked_depth += 1
            return
        if self._blocked_depth or tag not in ALLOWED_TAGS:
            return
        cleaned_attrs: list[tuple[str, str]] = []
        for name, value in attrs:
            attr = name.lower()
            raw = (value or "").strip()
            if tag == "a" and attr == "href" and _safe_href(raw):
                cleaned_attrs.append(("href", raw))
            elif attr == "style":
                style = _sanitize_style(raw)
                if style:
                    cleaned_attrs.append(("style", style))
        rendered_attrs = "".join(
            f' {name}="{escape(value, quote=True)}"' for name, value in cleaned_attrs
        )
        self.parts.append(f"<{tag}{rendered_attrs}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in BLOCKED_TAGS:
            return
        self.handle_starttag(tag, attrs)
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in BLOCKED_TAGS and self._blocked_depth:
            self._blocked_depth -= 1
            return
        if self._blocked_depth or tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._blocked_depth:
            self.parts.append(escape(data))

    def getvalue(self) -> str:
        return "".join(self.parts)


def _safe_href(value: str) -> bool:
    if not value or len(value) > 500:
        return False
    parsed = urlsplit(value)
    return parsed.scheme.lower() in {"http", "https", "mailto"} and bool(
        parsed.netloc or parsed.scheme.lower() == "mailto"
    )


def _sanitize_style(value: str) -> str:
    if not value or UNSAFE_STYLE_CONTENT.search(value):
        return ""
    declarations: list[str] = []
    for item in value.split(";"):
        if ":" not in item:
            continue
        name, raw_value = item.split(":", 1)
        prop = name.strip().lower()
        cleaned = " ".join(raw_value.strip().split())
        if prop not in ALLOWED_STYLE_PROPERTIES or not cleaned or len(cleaned) > 120:
            continue
        if UNSAFE_STYLE_CONTENT.search(cleaned):
            continue
        declarations.append(f"{prop}: {cleaned}")
    return "; ".join(declarations)


def contains_unsafe_email_html(value: str) -> bool:
    return bool(UNSAFE_HTML_CONTENT.search(value or ""))


def sanitize_email_html(value: str) -> str:
    parser = _EmailHTMLSanitizer()
    parser.feed(value[:50000])
    parser.close()
    return parser.getvalue().strip()


class _EmailTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs) -> None:
        if tag in {"p", "div", "li", "h1", "h2", "h3", "blockquote", "pre", "br"}:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("• ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "li", "h1", "h2", "h3", "blockquote", "pre", "ul", "ol"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def getvalue(self) -> str:
        text = "".join(self.parts)
        lines = [" ".join(line.split()) for line in text.splitlines()]
        compacted: list[str] = []
        blank = False
        for line in lines:
            if not line:
                if not blank:
                    compacted.append("")
                blank = True
                continue
            compacted.append(line)
            blank = False
        return "\n".join(compacted).strip()


def email_html_to_text(value: str) -> str:
    parser = _EmailTextExtractor()
    parser.feed(value)
    parser.close()
    return parser.getvalue()


def template_definition(key: str) -> MailTemplateDefinition:
    return MAIL_TEMPLATE_DEFINITION_MAP[key]


def template_variables(key: str) -> tuple[MailTemplateVariable, ...]:
    return template_definition(key).variables


def extract_placeholders(value: str) -> set[str]:
    return set(PLACEHOLDER.findall(value or ""))


def unknown_placeholders(key: str, value: str) -> set[str]:
    allowed = {variable.name for variable in template_variables(key)}
    return extract_placeholders(value) - allowed


def missing_required_placeholders(key: str, value: str) -> set[str]:
    used = extract_placeholders(value)
    return {
        variable.name
        for variable in template_variables(key)
        if variable.required and variable.name not in used
    }


def clean_email_subject(value: str) -> str:
    cleaned = " ".join((value or "").strip().split())
    if "\r" in value or "\n" in value:
        raise ValueError("邮件主题不能包含换行。")
    if not cleaned:
        raise ValueError("请输入邮件主题。")
    if len(cleaned) > 150:
        raise ValueError("邮件主题不能超过 150 个字符。")
    return cleaned


def ensure_default_mail_templates() -> int:
    existing = {
        key for key in db.session.scalars(db.select(MailTemplate.key)).all()
    }
    added = 0
    for definition in MAIL_TEMPLATE_DEFINITIONS:
        if definition.key in existing:
            continue
        db.session.add(
            MailTemplate(
                key=definition.key,
                name=definition.name,
                subject=definition.subject,
                body_html=definition.body_html,
            )
        )
        added += 1
    return added


def list_mail_templates() -> list[MailTemplate]:
    order = {definition.key: index for index, definition in enumerate(MAIL_TEMPLATE_DEFINITIONS)}
    items = db.session.scalars(db.select(MailTemplate)).all()
    return sorted(items, key=lambda item: order.get(item.key, len(order)))


def get_mail_template(key: str) -> MailTemplate | None:
    if key not in MAIL_TEMPLATE_KEYS:
        return None
    return db.session.scalar(db.select(MailTemplate).where(MailTemplate.key == key))


def effective_mail_template(key: str):
    row = get_mail_template(key)
    if row is not None:
        return row
    definition = template_definition(key)
    return SimpleNamespace(
        key=definition.key,
        name=definition.name,
        subject=definition.subject,
        body_html=definition.body_html,
        updated_at=None,
    )


def template_is_custom(item: MailTemplate) -> bool:
    definition = template_definition(item.key)
    return item.subject != definition.subject or item.body_html != definition.body_html


def reset_mail_template(item: MailTemplate) -> None:
    definition = template_definition(item.key)
    item.name = definition.name
    item.subject = definition.subject
    item.body_html = definition.body_html


# 改名前播种的默认模板正文；命中时一次性升级为当前默认值，自定义内容不受影响。
_LEGACY_MAIL_TEMPLATE_BODIES = {
    "smtp_test": (
        "<h1>{{ app_name }}邮件服务测试</h1>"
        "<p>这是一封由云门管理员后台发送的测试邮件。</p>"
        "<p>如果你看到这封邮件，说明当前SMTP连接可以正常发送邮件。</p>"
        "<p>测试时间：{{ tested_at }}</p>"
    ),
    "admin_email_verification": _code_html("验证云门管理员邮箱"),
    "registration": _code_html("创建云门账号"),
    "account_email_verification": _code_html("验证云门账号的当前邮箱"),
    "change_email": _code_html("更换云门账号邮箱"),
    "password_reset": _code_html("找回云门账号密码"),
}


def upgrade_legacy_mail_templates() -> int:
    upgraded = 0
    for key, legacy_body in _LEGACY_MAIL_TEMPLATE_BODIES.items():
        row = get_mail_template(key)
        if row is None or row.body_html != legacy_body:
            continue
        definition = template_definition(key)
        row.subject = definition.subject
        row.body_html = definition.body_html
        upgraded += 1
    return upgraded


def _render_placeholders(value: str, variables: dict[str, object], *, escape_html: bool) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            return ""
        rendered = str(variables[name])
        return escape(rendered) if escape_html else rendered

    return PLACEHOLDER.sub(replace, value or "")


def sample_template_variables(key: str) -> dict[str, str]:
    values = {variable.name: variable.sample for variable in template_variables(key)}
    values.setdefault("app_name", str(current_app.config.get("APP_NAME", "baka网关")))
    values.setdefault("issuer", str(current_app.config.get("OIDC_ISSUER", "")))
    values.setdefault("current_year", str(datetime.now().year))
    return values


def render_email_template(key: str, variables: dict[str, object]) -> tuple[str, str, str]:
    item = effective_mail_template(key)
    subject = clean_email_subject(_render_placeholders(item.subject, variables, escape_html=False))
    html_body = sanitize_email_html(_render_placeholders(item.body_html, variables, escape_html=True))
    text_body = email_html_to_text(html_body)
    if not html_body or not text_body:
        raise ValueError("邮件正文不能为空。")
    return subject, html_body, text_body
