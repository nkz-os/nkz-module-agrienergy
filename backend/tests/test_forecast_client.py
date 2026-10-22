"""ForecastClient — weather-api call carries the platform signature."""

import httpx
from nkz_platform_sdk.crypto import verify_hmac_signature

from app.services.forecast_client import ForecastClient


async def _headers_sent(monkeypatch, secret):
    if secret is None:
        monkeypatch.delenv("HMAC_SECRET", raising=False)
    else:
        monkeypatch.setenv("HMAC_SECRET", secret)
    seen = {}

    def handler(req):
        seen["headers"] = req.headers
        return httpx.Response(200, json={"forecast": []})

    fc = ForecastClient("t1", weather_api_url="http://w")
    fc._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await fc.fetch_solar_1h("p1")
    await fc._client.aclose()
    return seen["headers"]


async def test_request_is_signed(monkeypatch):
    """weather-api trusts X-Tenant-ID only with a valid platform signature."""
    headers = await _headers_sent(monkeypatch, "k")
    assert headers["x-tenant-id"] == "t1"
    assert verify_hmac_signature("k", headers["x-auth-signature"], "", "t1")


async def test_unsigned_without_secret(monkeypatch):
    headers = await _headers_sent(monkeypatch, None)
    assert "x-auth-signature" not in headers
