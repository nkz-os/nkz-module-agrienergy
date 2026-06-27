"""Keycloak client-credentials JWT for cron/worker → timeseries-reader."""

from __future__ import annotations

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

_jwt_cache: dict[str, object] = {"token": None, "exp": 0.0}


def _keycloak_token_url() -> str:
    base = os.getenv("KEYCLOAK_URL", "http://keycloak-service:8080/auth").rstrip("/")
    if not base.endswith("/auth"):
        base = f"{base}/auth"
    realm = os.getenv("KEYCLOAK_REALM", "nekazari")
    return f"{base}/realms/{realm}/protocol/openid-connect/token"


def _client_credentials() -> tuple[str, str]:
    client_id = (
        os.getenv("WORKER_KEYCLOAK_CLIENT_ID", "").strip()
        or os.getenv("GATEWAY_KEYCLOAK_CLIENT_ID", "").strip()
    )
    client_secret = (
        os.getenv("WORKER_KEYCLOAK_CLIENT_SECRET", "").strip()
        or os.getenv("GATEWAY_KEYCLOAK_CLIENT_SECRET", "").strip()
    )
    return client_id, client_secret


def obtain_worker_service_jwt() -> str | None:
    """Mint (or return cached) service JWT for multi-tenant worker calls."""
    now = time.time()
    cached = _jwt_cache.get("token")
    exp = float(_jwt_cache.get("exp") or 0)
    if isinstance(cached, str) and cached and exp > now + 30:
        return cached

    client_id, client_secret = _client_credentials()
    if not client_id or not client_secret:
        logger.warning("worker auth: client credentials not configured")
        return None

    try:
        resp = httpx.post(
            _keycloak_token_url(),
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=15.0,
        )
        if resp.status_code != 200:
            logger.error(
                "worker auth: Keycloak token failed %s %s",
                resp.status_code,
                resp.text[:200],
            )
            return None
        data = resp.json()
        token = data.get("access_token")
        if not token:
            return None
        expires_in = int(data.get("expires_in") or 300)
        _jwt_cache["token"] = token
        _jwt_cache["exp"] = now + max(60, expires_in)
        return token
    except httpx.HTTPError as exc:
        logger.error("worker auth: Keycloak request failed: %s", exc)
        return None
