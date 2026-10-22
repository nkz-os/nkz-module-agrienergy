"""Canonical HMAC signature for inter-service calls (matches nkz keycloak_auth)."""

from __future__ import annotations

import hashlib
import hmac
import os
import time


def generate_hmac_signature(token: str, tenant_id: str, timestamp: int | None = None) -> str:
    """Return ``{hexdigest}:{timestamp}`` (signature first)."""
    ts = int(timestamp if timestamp is not None else time.time())
    message = f"{token}|{tenant_id}|{ts}"
    secret = os.getenv("HMAC_SECRET", "")
    if not secret:
        return ""
    digest = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{digest}:{ts}"
