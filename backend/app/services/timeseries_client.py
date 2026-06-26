"""Authenticated read client for timeseries-reader (worker / cron use)."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.services.platform_hmac import generate_hmac_signature

logger = logging.getLogger(__name__)

POWER_ATTRIBUTES = ("measuredPowerW", "powerW", "measured_w", "power_w")


class TimeseriesReaderClient:
    """Query telemetry power series via timeseries-reader v2 API."""

    def __init__(
        self,
        tenant_id: str,
        base_url: str | None = None,
        bearer_token: str | None = None,
    ):
        self.tenant_id = tenant_id
        self.base_url = (
            base_url
            or os.getenv("TIMESERIES_READER_URL", "http://timeseries-reader-service:5000")
        ).rstrip("/")
        self.bearer_token = (bearer_token or os.getenv("WORKER_BEARER_TOKEN", "")).strip()
        self._client = httpx.AsyncClient(timeout=60.0)

    def _headers(self) -> dict[str, str]:
        headers = {
            "X-Tenant-ID": self.tenant_id,
            "NGSILD-Tenant": self.tenant_id,
            "Fiware-Service": self.tenant_id,
            "X-User-ID": "agrienergy-daily-aggregation",
            "Content-Type": "application/json",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
            sig = generate_hmac_signature(self.bearer_token, self.tenant_id)
            if sig:
                headers["X-Auth-Signature"] = sig
        return headers

    async def fetch_power_series(
        self,
        entity_id: str,
        since: datetime,
        until: datetime,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """Return normalised ``[{ts, value}]`` for the first attribute with data."""
        if not self.bearer_token:
            logger.warning(
                "timeseries: WORKER_BEARER_TOKEN unset — cannot query %s (tenant=%s)",
                entity_id, self.tenant_id,
            )
            return []

        since_s = since.isoformat().replace("+00:00", "Z")
        until_s = until.isoformat().replace("+00:00", "Z")
        encoded = quote(entity_id, safe="")

        for attr in POWER_ATTRIBUTES:
            url = f"{self.base_url}/api/timeseries/v2/entities/{encoded}/data"
            params = {
                "time_from": since_s,
                "time_to": until_s,
                "attrs": attr,
                "limit": limit,
            }
            try:
                resp = await self._client.get(url, params=params, headers=self._headers())
                if resp.status_code == 400:
                    continue
                resp.raise_for_status()
                body = resp.json()
                points = _normalise_columnar(body, attr)
                if points:
                    return points
            except httpx.HTTPError as exc:
                logger.debug(
                    "timeseries %s attr=%s failed: %s", entity_id, attr, exc)
        return []

    async def close(self) -> None:
        await self._client.aclose()


def _normalise_columnar(body: dict, attr: str) -> list[dict[str, Any]]:
    """Convert timeseries-reader columnar JSON to point list."""
    timestamps = body.get("timestamps") or []
    attrs = body.get("attributes") or {}
    values = attrs.get(attr) or []
    out: list[dict[str, Any]] = []
    for ts, val in zip(timestamps, values):
        if ts is None or val is None:
            continue
        try:
            out.append({"ts": str(ts), "value": float(val)})
        except (TypeError, ValueError):
            continue
    return out
