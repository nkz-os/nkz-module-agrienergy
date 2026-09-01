"""ElevationService cascade: LiDAR DTM -> eu-elevation -> fail-safe zeros."""

import httpx
import pytest

from app.engines.elevation import ElevationService, ElevationUnavailableError

POS = [(-2.0, 43.3), (-2.001, 43.301)]


def install_transport(monkeypatch, handler):
    """Patch httpx.AsyncClient so internally-created clients hit our handler."""
    real_client = httpx.AsyncClient

    def fake_client(**kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)


@pytest.mark.asyncio
async def test_eu_elevation_happy_path(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/api/elevation/point" in str(request.url)
        # tenant header forwarded
        assert request.headers.get("X-Tenant-ID") == "asociacion-allotarra"
        lat = float(request.url.params["lat"])
        return httpx.Response(200, json={"elevation_m": 100.0 + lat})

    install_transport(monkeypatch, handler)
    svc = ElevationService(tenant_id="asociacion-allotarra")
    out = await svc.get_elevations(POS)
    assert len(out) == 2
    assert out[0] == pytest.approx(143.3)
    # POS[1] = (lon=-2.001, lat=43.301) → eu-elevation receives lat=43.301
    # → elevation_m = 100.0 + 43.301 = 143.301
    assert out[1] == pytest.approx(143.301)


@pytest.mark.asyncio
async def test_no_parcel_skips_lidar(monkeypatch):
    seen_urls = []

    def handler(request):
        seen_urls.append(str(request.url))
        return httpx.Response(200, json={"elevation_m": 50.0})

    install_transport(monkeypatch, handler)
    out = await ElevationService("t").get_elevations(POS, parcel_id="")
    assert all("/lidar" not in u for u in seen_urls)
    assert out == [50.0, 50.0]


@pytest.mark.asyncio
async def test_lidar_without_dtm_falls_to_eu_elevation(monkeypatch):
    def handler(request):
        url = str(request.url)
        if "/lidar/layers" in url:
            return httpx.Response(200, json={"layers": [{"id": "l1", "products": ["dsm"]}]})
        if "/elevation/point" in url:
            return httpx.Response(200, json={"elevation_m": 77.0})
        return httpx.Response(404)

    install_transport(monkeypatch, handler)
    out = await ElevationService("t").get_elevations(POS, parcel_id="urn:p1")
    assert out == [77.0, 77.0]


@pytest.mark.asyncio
async def test_lidar_error_falls_to_eu_elevation(monkeypatch):
    def handler(request):
        url = str(request.url)
        if "/lidar/" in url:
            return httpx.Response(500)
        return httpx.Response(200, json={"elevation_m": 33.0})

    install_transport(monkeypatch, handler)
    out = await ElevationService("t").get_elevations(POS, parcel_id="urn:p1")
    assert out == [33.0, 33.0]


@pytest.mark.asyncio
async def test_eu_elevation_null_returns_failsafe_zeros(monkeypatch):
    """eu-elevation may answer elevation_m:null (status unavailable); must not raise."""
    def handler(request):
        assert "/api/elevation/point" in str(request.url)
        return httpx.Response(
            200, json={"elevation_m": None, "status": "unavailable"}
        )

    install_transport(monkeypatch, handler)
    out = await ElevationService("t").get_elevations(POS)
    assert out == [0.0, 0.0]  # failsafe, never raises, never None


@pytest.mark.asyncio
async def test_query_single_raises_on_null_elevation(monkeypatch):
    """Null elevation is surfaced explicitly as ElevationUnavailableError, not a TypeError."""
    def handler(request):
        return httpx.Response(
            200, json={"elevation_m": None, "status": "unavailable"}
        )

    install_transport(monkeypatch, handler)
    svc = ElevationService("t")
    with pytest.raises(ElevationUnavailableError):
        async with httpx.AsyncClient() as client:
            await svc._query_single(client, lat=43.3, lon=-2.0)


@pytest.mark.asyncio
async def test_everything_down_failsafe_zeros(monkeypatch):
    def handler(request):
        return httpx.Response(503)

    install_transport(monkeypatch, handler)
    out = await ElevationService("t").get_elevations(POS, parcel_id="urn:p1")
    assert out == [0.0, 0.0]  # never raises, never None


@pytest.mark.asyncio
async def test_empty_positions(monkeypatch):
    out = await ElevationService("t").get_elevations([])
    assert out == []


@pytest.mark.asyncio
async def test_duplicate_positions_single_query(monkeypatch):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"elevation_m": 10.0})

    install_transport(monkeypatch, handler)
    out = await ElevationService("t").get_elevations([POS[0], POS[0], POS[0]])
    assert out == [10.0, 10.0, 10.0]
    assert len(calls) == 1  # dedup
