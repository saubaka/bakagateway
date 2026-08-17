from __future__ import annotations

import json
import re

from app.extensions import db
from app.models import SiteSetting

PAGE_TRANSITION_CHOICES = (
    ("stretch", "左侧拉伸"),
    ("fade", "直接浮现"),
    ("zoom-blur", "缩放与模糊"),
    ("none", "无动画"),
)
PAGE_TRANSITION_VALUES = frozenset(value for value, _label in PAGE_TRANSITION_CHOICES)

DIALOG_STYLE_CHOICES = (
    ("soft", "柔和圆角"),
    ("glass", "轻透玻璃"),
    ("paper", "纸张卡片"),
    ("compact", "紧凑浮层"),
    ("cloud", "云朵气泡"),
    ("outline", "轻线留白"),
)
DIALOG_STYLE_VALUES = frozenset(value for value, _label in DIALOG_STYLE_CHOICES)
DIALOG_SHADOW_CHOICES = (
    ("none", "无阴影"),
    ("light", "轻柔"),
    ("soft", "标准"),
    ("deep", "深层悬浮"),
)
DIALOG_SHADOW_VALUES = frozenset(value for value, _label in DIALOG_SHADOW_CHOICES)

GLOBAL_FONT_CHOICES = (
    ("cloud-rounded", "云朵圆体"),
    ("candy-soft", "糖霜柔体"),
    ("playful-yuan", "软糖幼圆"),
    ("diary-serif", "手账宋体"),
    ("starlight-kaiti", "星光楷体"),
    ("neumorphic-clean", "清透拟态"),
)
GLOBAL_FONT_VALUES = frozenset(value for value, _label in GLOBAL_FONT_CHOICES)

THEME_DEFAULTS = {
    "global_font_style": "cloud-rounded",
    "page_transition_style": "stretch",
    "page_transition_duration": "720",
    "page_transition_color_start": "#eaf6ff",
    "page_transition_color_middle": "#f9fbff",
    "page_transition_color_end": "#fceef6",
    "dialog_style": "soft",
    "dialog_color_start": "#ffffff",
    "dialog_color_end": "#fff1f7",
    "dialog_accent": "#7eaed0",
    "dialog_radius": "30",
    "dialog_width": "510",
    "dialog_backdrop_blur": "6",
    "dialog_shadow": "soft",
    "admin_menu_subtitles_visible": "true",
}
FOOTER_DEFAULT = {
    "description": "一个温柔而可靠的统一登录入口。",
    "copyright": "本地优先 · 安全可控 · 柔和响应",
    "columns": [
        {
            "title": "baka网关",
            "links": [
                {"label": "我的主页", "url": "/portal/"},
                {"label": "账号安全", "url": "/portal/security/"},
            ],
        }
    ],
}
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
SAFE_FOOTER_URL = re.compile(r"^(?:https?://|mailto:|/|#)", re.IGNORECASE)


def get_setting(key: str, default: str = "") -> str:
    item = db.session.get(SiteSetting, key)
    return item.value if item is not None else default


def set_setting(key: str, value: str) -> None:
    item = db.session.get(SiteSetting, key)
    if item is None:
        db.session.add(SiteSetting(key=key, value=value))
    else:
        item.value = value


def _choice(key: str, allowed: frozenset[str]) -> str:
    value = get_setting(key, THEME_DEFAULTS[key])
    return value if value in allowed else THEME_DEFAULTS[key]


def _integer(key: str, minimum: int, maximum: int) -> int:
    try:
        value = int(get_setting(key, THEME_DEFAULTS[key]))
    except (TypeError, ValueError):
        value = int(THEME_DEFAULTS[key])
    return max(minimum, min(maximum, value))


def _color(key: str) -> str:
    value = get_setting(key, THEME_DEFAULTS[key]).lower()
    return value if HEX_COLOR.fullmatch(value) else THEME_DEFAULTS[key]


def load_theme_settings() -> dict[str, str | int | bool]:
    return {
        "global_font_style": _choice("global_font_style", GLOBAL_FONT_VALUES),
        "page_transition_style": _choice(
            "page_transition_style", PAGE_TRANSITION_VALUES
        ),
        "page_transition_duration": _integer(
            "page_transition_duration", 300, 2400
        ),
        "page_transition_color_start": _color("page_transition_color_start"),
        "page_transition_color_middle": _color("page_transition_color_middle"),
        "page_transition_color_end": _color("page_transition_color_end"),
        "dialog_style": _choice("dialog_style", DIALOG_STYLE_VALUES),
        "dialog_color_start": _color("dialog_color_start"),
        "dialog_color_end": _color("dialog_color_end"),
        "dialog_accent": _color("dialog_accent"),
        "dialog_radius": _integer("dialog_radius", 14, 42),
        "dialog_width": _integer("dialog_width", 360, 720),
        "dialog_backdrop_blur": _integer("dialog_backdrop_blur", 0, 30),
        "dialog_shadow": _choice("dialog_shadow", DIALOG_SHADOW_VALUES),
        "admin_menu_subtitles_visible": get_setting(
            "admin_menu_subtitles_visible",
            THEME_DEFAULTS["admin_menu_subtitles_visible"],
        )
        .strip()
        .lower()
        in {"1", "true", "yes", "on"},
    }


def load_footer_content() -> dict:
    raw = get_setting("footer_content", "")
    try:
        value = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    columns = value.get("columns")
    if not isinstance(columns, list):
        columns = FOOTER_DEFAULT["columns"]
    clean_columns = []
    for column in columns[:8]:
        if not isinstance(column, dict):
            continue
        links = []
        for link in column.get("links", [])[:10]:
            if not isinstance(link, dict):
                continue
            label = str(link.get("label", "")).strip()[:40]
            url = str(link.get("url", "")).strip()[:500]
            if label and url and SAFE_FOOTER_URL.match(url):
                links.append({"label": label, "url": url})
        title = str(column.get("title", "")).strip()[:60]
        if title:
            clean_columns.append({"title": title, "links": links})
    return {
        "description": str(
            value.get("description", FOOTER_DEFAULT["description"])
        ).strip()[:300],
        "copyright": str(
            value.get("copyright", FOOTER_DEFAULT["copyright"])
        ).strip()[:255],
        "columns": clean_columns,
    }


def save_footer_content(value: dict) -> None:
    set_setting("footer_content", json.dumps(value, ensure_ascii=False))
