"""Chặn secret trong ConfigVersion (M04A-01): từ chối khoá giống secret ở MỌI vùng config.

Giá trị của config được lưu DB và trả lại trong response, nên khoá như `api_key`, `secret`,
`token`, `password`, `authorization` không được phép ở bất kỳ độ sâu nào của engines/thresholds/
models. Ngoại lệ duy nhất: `models.vlm.api_key_env` (chỉ là TÊN biến môi trường, đã có allowlist).
Đây là kiểm tên khoá; không thể phát hiện secret dán vào giá trị tự do.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SECRET_SUBSTRINGS = (
    "apikey",
    "secret",
    "password",
    "passwd",
    "authorization",
    "credential",
    "bearer",
    "privatekey",
    "accesskey",
)
_SECRET_EXACT = frozenset(
    {"token", "accesstoken", "authtoken", "refreshtoken", "idtoken", "sessiontoken", "cookie"}
)
_NON_ALNUM = re.compile(r"[^a-z0-9]")
MAX_DEPTH = 12


def is_secret_like_key(key: str) -> bool:
    normalized = _NON_ALNUM.sub("", key.lower())
    return normalized in _SECRET_EXACT or any(s in normalized for s in _SECRET_SUBSTRINGS)


_EXEMPT_PATH = ("models", "vlm", "api_key_env")


def find_secret_keys(value: Any, path: tuple[str, ...] = (), depth: int = 0) -> list[str]:
    """Đường dẫn các khoá giống secret (không bao giờ trả giá trị).

    Đường dẫn là tuple cấu trúc (không nối bằng dấu chấm) nên khoá có dấu chấm như
    "vlm.api_key_env" không thể giả mạo ngoại lệ; ngoại lệ chỉ đúng ("models","vlm","api_key_env").
    """
    found: list[str] = []
    shown = ".".join(path) or "<root>"
    if depth > MAX_DEPTH:
        return [f"{shown} (quá sâu)"]
    if isinstance(value, Mapping):
        for key, child in value.items():
            name = str(key)
            child_path = (*path, name)
            if is_secret_like_key(name) and child_path != _EXEMPT_PATH:
                found.append(".".join(child_path))
            found += find_secret_keys(child, child_path, depth + 1)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found += find_secret_keys(child, (*path, f"[{index}]"), depth + 1)
    return found


def validate_config_safety(
    engines: Mapping[str, Any], thresholds: Mapping[str, Any], models: Mapping[str, Any]
) -> list[str]:
    tree = {"engines": engines, "thresholds": thresholds, "models": models}
    return [
        f"{path}: khoá giống secret không được lưu trong config." for path in find_secret_keys(tree)
    ]
