"""Short-horizon solar forecast for MPC context (fail-safe, no blocking)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

FORECAST_TIMEOUT_S = 2.0


class ForecastClient:
    """Fetch parcel-level solar irradiance proxy for the next hour."""

    def __init__(
        self,
        tenant_id: str,
        weather_api_url: str | None = None,
    ):
        self.tenant_id = tenant_id
        self.weather_api_url = (
            weather_api_url
            or os.getenv("WEATHER_API_URL", "http://weather-api-service:8000")
        ).rstrip("/")
        self._client = httpx.AsyncClient(timeout=FORECAST_TIMEOUT_S)

    async def fetch_solar_1h(
        self,
        parcel_id: str,
        *,
        fallback_ghi: float | None = None,
    ) -> dict[str, Any]:
        """Return ``{ ghi_1h, dni_1h, dhi_1h, horizon_minutes, source }`` or empty on failure."""
        try:
            url = f"{self.weather_api_url}/api/weather/parcel/{parcel_id}/forecast"
            resp = await self._client.get(
                url,
                params={"days": 1},
                headers={"X-Tenant-ID": self.tenant_id},
            )
            if resp.status_code != 200:
                return _fallback(fallback_ghi, "weather-api-error")
            body = resp.json()
            forecast = body.get("forecast") or []
            if not forecast:
                return _fallback(fallback_ghi, "empty-forecast")

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            entry = next((f for f in forecast if f.get("date") == today), forecast[0])
            ghi = entry.get("solar_rad_w_m2")
            if ghi is None:
                return _fallback(fallback_ghi, "no-solar-field")

            ghi_f = float(ghi)
            # Erbs-style split for plane-of-array inputs (approximate).
            dni = ghi_f * 0.65
            dhi = ghi_f * 0.35
            return {
                "ghi_1h": ghi_f,
                "dni_1h": dni,
                "dhi_1h": dhi,
                "horizon_minutes": 60,
                "source": body.get("source", "weather-api"),
            }
        except Exception as exc:
            logger.debug("forecast fetch failed parcel=%s: %s", parcel_id, exc)
            return _fallback(fallback_ghi, "exception")

    async def close(self) -> None:
        await self._client.aclose()


def _fallback(ghi: float | None, source: str) -> dict[str, Any]:
    if ghi is None or ghi <= 0:
        return {}
    ghi_f = float(ghi)
    return {
        "ghi_1h": ghi_f,
        "dni_1h": ghi_f * 0.65,
        "dhi_1h": ghi_f * 0.35,
        "horizon_minutes": 60,
        "source": f"fallback-{source}",
    }
