"""Versioned VLM settings and encrypted credentials shared by API and workers."""

from __future__ import annotations

import base64
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.utils.crypto import salted_hmac

from runs.models import VlmConfiguration, VlmConnection
from vlm.config import VlmConfig
from vlm.errors import VlmProviderError, VlmProviderFailure


def credential_cipher() -> MultiFernet:
    # Domain-separated derivation from Django's high-entropy deployment secret.
    # Fallback secrets permit Django SECRET_KEY rotation without losing stored keys.
    secrets = [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]
    return MultiFernet(
        [
            Fernet(
                base64.urlsafe_b64encode(
                    salted_hmac(
                        "labelx.vlm.credentials.v1", "encryption", secret=secret, algorithm="sha256"
                    ).digest()
                )
            )
            for secret in secrets
        ]
    )


def current_config() -> dict[str, Any] | None:
    pointer = VlmConfiguration.objects.select_related("connection").filter(pk=1).first()
    if pointer is None or pointer.connection is None:
        return None
    return {**pointer.connection.config, "connection_id": pointer.connection_id}


def connection_api_key(config: VlmConfig) -> str:
    if config.connection_id is None:
        raise VlmProviderError(VlmProviderFailure.AUTH, "Chưa chọn kết nối VLM.")
    connection = VlmConnection.objects.filter(pk=config.connection_id).first()
    if connection is None or any(
        connection.config.get(field) != getattr(config, field)
        for field in ("provider", "base_url", "model", "api_key_env")
    ):
        raise VlmProviderError(VlmProviderFailure.AUTH, "Kết nối VLM không khớp cấu hình run.")
    try:
        return credential_cipher().decrypt(connection.encrypted_api_key.encode()).decode()
    except (InvalidToken, UnicodeError):
        raise VlmProviderError(VlmProviderFailure.AUTH, "Không giải mã được API key VLM.") from None
