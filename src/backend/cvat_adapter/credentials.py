"""Encrypted personal credentials with the deployment token as a fallback."""

import base64

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.crypto import salted_hmac

from accounts.models import CvatProfile
from cvat_adapter.client import CvatConfigurationError


def credential_cipher() -> MultiFernet:
    return MultiFernet(
        [
            Fernet(
                base64.urlsafe_b64encode(
                    salted_hmac(
                        "labelx.cvat.credentials.v1",
                        "encryption",
                        secret=secret,
                        algorithm="sha256",
                    ).digest()
                )
            )
            for secret in [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]
        ]
    )


def service_token(user: User | None = None) -> str:
    profile = CvatProfile.objects.filter(user=user).first() if user is not None else None
    if profile is None:
        return str(settings.CVAT_SERVICE_TOKEN)
    try:
        return credential_cipher().decrypt(profile.encrypted_token.encode()).decode()
    except (InvalidToken, UnicodeError):
        raise CvatConfigurationError("Không giải mã được token CVAT trong Hồ sơ.") from None
