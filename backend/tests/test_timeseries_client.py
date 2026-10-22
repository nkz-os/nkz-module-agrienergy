"""TimeseriesReaderClient auth header tests."""

from unittest.mock import patch

from app.services.timeseries_client import TimeseriesReaderClient


def test_delegated_tenant_headers_when_service_jwt():
    with patch(
        "app.services.timeseries_client.obtain_worker_service_jwt",
        return_value="svc-jwt",
    ):
        client = TimeseriesReaderClient("tenant-a")
    headers = client._headers()
    assert headers["Authorization"] == "Bearer svc-jwt"
    assert headers["X-Delegated-Tenant-ID"] == "tenant-a"
    assert "X-Tenant-ID" not in headers
    assert "X-Auth-Signature" not in headers


def test_static_token_uses_hmac_when_not_delegated(monkeypatch):
    monkeypatch.setenv("WORKER_BEARER_TOKEN", "user-jwt")
    monkeypatch.setenv("HMAC_SECRET", "test-secret")
    monkeypatch.delenv("WORKER_USE_DELEGATED_TENANT", raising=False)
    client = TimeseriesReaderClient("tenant-b")
    headers = client._headers()
    assert headers["X-Tenant-ID"] == "tenant-b"
    assert "X-Delegated-Tenant-ID" not in headers
    assert headers["X-Auth-Signature"].count(":") == 1
