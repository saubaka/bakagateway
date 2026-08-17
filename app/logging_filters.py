"""Logging filters that keep authentication material out of access logs."""

from __future__ import annotations

import logging
import re

REQUEST_LINE_PATTERN = re.compile(
    r"(?P<method>GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) "
    r"(?P<target>/\S+?) "
    r"(?P<protocol>HTTP/\d(?:\.\d)?)",
)
SENSITIVE_QUERY_PATTERN = re.compile(
    r"(?:[?&]|%3F|%26)"
    r"(?:code|state|nonce|code_challenge|code_verifier|client_secret|"
    r"access_token|refresh_token)"
    r"(?:=|%3D)",
    re.IGNORECASE,
)


def sanitize_request_line(value: str) -> str:
    """Replace an authentication-bearing request query with one marker."""

    match = REQUEST_LINE_PATTERN.search(value)
    if match is None:
        return value
    target = match.group("target")
    if "?" not in target or SENSITIVE_QUERY_PATTERN.search(target) is None:
        return value
    sanitized_target = f"{target.split('?', 1)[0]}?<redacted>"
    return value[: match.start("target")] + sanitized_target + value[match.end("target") :]


class SensitiveQueryFilter(logging.Filter):
    """Sanitize Werkzeug request-line messages before handlers render them."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = sanitize_request_line(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                sanitize_request_line(item) if isinstance(item, str) else item
                for item in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: sanitize_request_line(item) if isinstance(item, str) else item
                for key, item in record.args.items()
            }
        return True


def install_werkzeug_sensitive_query_filter() -> None:
    """Install one process-wide filter on the Werkzeug access logger."""

    logger = logging.getLogger("werkzeug")
    if not any(isinstance(item, SensitiveQueryFilter) for item in logger.filters):
        logger.addFilter(SensitiveQueryFilter())
