"""Daily aggregation worker tests."""

from datetime import date

import pytest

from app.services.daily_aggregation import aggregate_tracker_day
from tests.conftest import OrionWorld, FakeOrionClient


class FakeTimeseries:
    def __init__(self, points: list[dict]):
        self.points = points
        self.calls: list[str] = []

    async def fetch_power_series(self, entity_id, since, until, limit=5000):
        self.calls.append(entity_id)
        return list(self.points)

    async def close(self):
        pass


class FakeFinBridge:
    def __init__(self):
        self.emitted: list[dict] = []

    async def emit_daily_aggregation(self, **kwargs):
        self.emitted.append(kwargs)


@pytest.mark.asyncio
async def test_aggregate_emits_wh_and_updates_orion(monkeypatch):
    world = OrionWorld()
    orion = FakeOrionClient(world, "tenant-a")
    tracker = {
        "id": "urn:ngsi-ld:AgriEnergyTracker:t1",
        "hasAgriParcel": {"object": "urn:ngsi-ld:AgriParcel:p1"},
    }
    points = [
        {"ts": "2026-06-25T10:00:00Z", "value": 500.0},
        {"ts": "2026-06-25T11:00:00Z", "value": 500.0},
    ]
    ts = FakeTimeseries(points)
    fin = FakeFinBridge()

    def fake_get_orion(tenant_id):
        return FakeOrionClient(world, tenant_id)

    monkeypatch.setattr("app.services.daily_aggregation.get_orion", fake_get_orion)

    result = await aggregate_tracker_day(
        "tenant-a", tracker, date(2026, 6, 25), ts, fin,
    )
    assert result["generation_wh"] == 500.0
    assert result["finbridge"] == "emitted"
    assert fin.emitted[0]["generation_wh"] == 500.0
    assert fin.emitted[0]["aggregation_date"] == date(2026, 6, 25)
    assert world.appended
    _, eid, attrs = world.appended[-1]
    assert eid == tracker["id"]
    assert attrs["dailyGenerationWh"]["value"] == 500.0


@pytest.mark.asyncio
async def test_aggregate_skips_without_series():
    ts = FakeTimeseries([])
    fin = FakeFinBridge()
    tracker = {
        "id": "urn:ngsi-ld:AgriEnergyTracker:t1",
        "hasAgriParcel": {"object": "urn:ngsi-ld:AgriParcel:p1"},
    }
    result = await aggregate_tracker_day(
        "tenant-a", tracker, date(2026, 6, 25), ts, fin,
        write_orion=False,
    )
    assert result["skipped"] is True
    assert fin.emitted == []
