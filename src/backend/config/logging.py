"""Structured, request-aware logging helpers for the LabelX backend."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

REDACTED = "[REDACTED]"

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_run_id: ContextVar[str | None] = ContextVar("run_id", default=None)
_snapshot_id: ContextVar[str | None] = ContextVar("snapshot_id", default=None)


class _Unset:
    pass


_UNSET = _Unset()

_SENSITIVE_KEY_RE = re.compile(
    r"(?:authorization|cookie|password|passwd|secret|token|api[_-]?key|"
    r"private[_-]?key|session[_-]?key)",
    re.IGNORECASE,
)
_SENSITIVE_FIELD = (
    r"authorization|proxy[-_ ]authorization|cookie|set[-_ ]cookie|password|passwd|secret|"
    r"token|access[-_ ]token|refresh[-_ ]token|cvat[-_ ]service[-_ ]token|"
    r"api[-_ ]key|x[-_ ]api[-_ ]key|private[-_ ]key|session[-_ ]key"
)
_QUOTED_SECRET_RE = re.compile(
    rf"(?P<prefix>[\"']?(?:{_SENSITIVE_FIELD})[\"']?\s*[:=]\s*)"
    r"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE,
)
_AUTHORIZATION_RE = re.compile(
    r"(?P<prefix>\b(?:authorization|proxy[-_ ]authorization)\b\s*[:=]\s*)"
    r"(?:(?:bearer|basic|token)\s+)?[^\s,;}\]]+",
    re.IGNORECASE,
)
_COOKIE_RE = re.compile(
    r"(?P<prefix>\b(?:cookie|set[-_ ]cookie)\b\s*[:=]\s*)[^\r\n,}]+",
    re.IGNORECASE,
)
_UNQUOTED_SECRET_RE = re.compile(
    rf"(?P<prefix>\b(?:{_SENSITIVE_FIELD})\b\s*[:=]\s*)[^\s,;}}&\]]+",
    re.IGNORECASE,
)
_AUTH_SCHEME_RE = re.compile(
    r"\b(?P<scheme>bearer|basic|token)\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE
)
_CONNECTION_URL_CREDENTIAL_RE = re.compile(
    r"(?P<scheme>\b[a-z][a-z0-9+.-]*://)(?P<username>[^/\s:@]+):(?P<password>[^@\s/]+)@",
    re.IGNORECASE,
)
_DUPLICATE_REDACTION_BRACKET_RE = re.compile(r"\[REDACTED\]\]+")

_STANDARD_LOG_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
}
_SKIPPED_EXTRA_FIELDS = {"request", "exc_info", "exc_text", "stack_info"}


def _context_value(value: object) -> str | None:
    return None if value is None else str(value)


@contextmanager
def log_context(
    *,
    request_id: object = _UNSET,
    run_id: object = _UNSET,
    snapshot_id: object = _UNSET,
) -> Iterator[None]:
    """Temporarily bind identifiers to every log record in the current context."""

    request_token: Token[str | None] | None = None
    run_token: Token[str | None] | None = None
    snapshot_token: Token[str | None] | None = None
    try:
        if request_id is not _UNSET:
            request_token = _request_id.set(_context_value(request_id))
        if run_id is not _UNSET:
            run_token = _run_id.set(_context_value(run_id))
        if snapshot_id is not _UNSET:
            snapshot_token = _snapshot_id.set(_context_value(snapshot_id))
        yield
    finally:
        if snapshot_token is not None:
            _snapshot_id.reset(snapshot_token)
        if run_token is not None:
            _run_id.reset(run_token)
        if request_token is not None:
            _request_id.reset(request_token)


def bind_log_context(*, run_id: object = _UNSET, snapshot_id: object = _UNSET) -> None:
    """Bind execution identifiers for the remainder of the current request/task context."""

    if run_id is not _UNSET:
        _run_id.set(_context_value(run_id))
    if snapshot_id is not _UNSET:
        _snapshot_id.set(_context_value(snapshot_id))


def redact_text(value: str) -> str:
    """Redact common secret representations without exposing their values."""

    value = _CONNECTION_URL_CREDENTIAL_RE.sub(
        lambda match: f"{match.group('scheme')}{match.group('username')}:{REDACTED}@",
        value,
    )
    value = _QUOTED_SECRET_RE.sub(
        lambda match: (
            f"{match.group('prefix')}{match.group('quote')}{REDACTED}{match.group('quote')}"
        ),
        value,
    )
    value = _AUTHORIZATION_RE.sub(lambda match: f"{match.group('prefix')}{REDACTED}", value)
    value = _COOKIE_RE.sub(lambda match: f"{match.group('prefix')}{REDACTED}", value)
    value = _UNQUOTED_SECRET_RE.sub(lambda match: f"{match.group('prefix')}{REDACTED}", value)
    value = _AUTH_SCHEME_RE.sub(lambda match: f"{match.group('scheme')} {REDACTED}", value)
    return _DUPLICATE_REDACTION_BRACKET_RE.sub(REDACTED, value)


def redact_value(value: object, *, key: object | None = None) -> object:
    """Recursively redact values associated with sensitive structured-log keys."""

    if key is not None and _SENSITIVE_KEY_RE.search(str(key)):
        return REDACTED
    if isinstance(value, Mapping):
        return {
            str(item_key): redact_value(item_value, key=item_key)
            for item_key, item_value in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, set):
        return [redact_value(item) for item in sorted(value, key=str)]
    if isinstance(value, str):
        return redact_text(value)
    return value


class RequestContextFilter(logging.Filter):
    """Attach request/execution context to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        request = getattr(record, "request", None)
        record.request_id = getattr(request, "request_id", None) or _request_id.get() or "-"
        record.run_id = getattr(request, "run_id", None) or _run_id.get()
        record.snapshot_id = getattr(request, "snapshot_id", None) or _snapshot_id.get()
        return True


class SecretRedactionFilter(logging.Filter):
    """Remove secrets before a record reaches any configured formatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            message = str(record.msg)
        record.msg = redact_text(message)
        record.args = ()

        for key, value in list(record.__dict__.items()):
            if key in _STANDARD_LOG_RECORD_FIELDS or key in _SKIPPED_EXTRA_FIELDS:
                continue
            setattr(record, key, redact_value(value, key=key))
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        return True


class JsonFormatter(logging.Formatter):
    """Serialize a log record as one compact JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
            "request_id": getattr(record, "request_id", "-"),
        }

        run_id = getattr(record, "run_id", None)
        snapshot_id = getattr(record, "snapshot_id", None)
        if run_id is not None:
            payload["run_id"] = run_id
        if snapshot_id is not None:
            payload["snapshot_id"] = snapshot_id

        for key, value in record.__dict__.items():
            if (
                key in _STANDARD_LOG_RECORD_FIELDS
                or key in _SKIPPED_EXTRA_FIELDS
                or key in payload
                or key.startswith("_")
            ):
                continue
            payload[key] = redact_value(value, key=key)

        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        if record.stack_info:
            payload["stack"] = redact_text(self.formatStack(record.stack_info))

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def _json_default(value: Any) -> str:
    return redact_text(str(value))
