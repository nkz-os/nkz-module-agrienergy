"""Tests for the crop-health water stress / shade reader."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import water_stress_reader as wsr
from app.services.water_stress_reader import (
    CropHealthState,
    biology_from_state,
    fetch_crop_health_state,
)

NOW = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
PARCEL = "urn:ngsi-ld:AgriParcel:p-1"


@pytest.fixture(autouse=True)
def _reset_cache():
    wsr.reset_cache()
    yield
    wsr.reset_cache()


def _state(**kw):
    base = dict(stress_index=0.83, fidelity="iot_sensor",
                observed_at=NOW - timedelta(seconds=60), shade_fraction=0.4)
    base.update(kw)
    return CropHealthState(**base)


def test_biology_for_fresh_iot_sensor():
    assert biology_from_state(_state(), max_age_s=3600, now=NOW) == {"stress_index": 0.83}


def test_biology_ignores_non_iot_fidelity():
    assert biology_from_state(_state(fidelity="parcel_weather"), max_age_s=3600, now=NOW) == {}


def test_biology_ignores_stale():
    st = _state(observed_at=NOW - timedelta(seconds=3601))
    assert biology_from_state(st, max_age_s=3600, now=NOW) == {}


def test_biology_boundary_age_is_fresh():
    st = _state(observed_at=NOW - timedelta(seconds=3600))
    assert biology_from_state(st, max_age_s=3600, now=NOW) == {"stress_index": 0.83}


def test_biology_future_within_300s_is_fresh():
    st = _state(observed_at=NOW + timedelta(seconds=300))
    assert biology_from_state(st, max_age_s=3600, now=NOW) == {"stress_index": 0.83}


def test_biology_future_beyond_300s_is_ignored():
    st = _state(observed_at=NOW + timedelta(seconds=301))
    assert biology_from_state(st, max_age_s=3600, now=NOW) == {}


def test_biology_none_and_missing_fields():
    assert biology_from_state(None, max_age_s=3600, now=NOW) == {}
    assert biology_from_state(_state(stress_index=None), max_age_s=3600, now=NOW) == {}
    assert biology_from_state(_state(observed_at=None), max_age_s=3600, now=NOW) == {}


def test_biology_never_contains_shade():
    out = biology_from_state(_state(shade_fraction=0.9), max_age_s=3600, now=NOW)
    assert "shade_fraction" not in out and "shadeFraction" not in out


def _entity(eid, index=0.5, fidelity="iot_sensor", observed="2026-10-22T11:00:00Z", shade=None,
            shade_observed=None):
    e = {"id": eid, "type": "CropHealthAssessment", "hasAgriParcel": PARCEL}
    if index is not None:
        e["waterStressIndex"] = index
    if fidelity is not None:
        e["waterStressFidelity"] = fidelity
    if observed is not None:
        e["waterStressObservedAt"] = observed
    if shade is not None:
        e["shadeFraction"] = shade
    if shade_observed is not None:
        e["shadeObservedAt"] = shade_observed
    return e


def _http_error(status):
    req = httpx.Request("GET", "http://broker.invalid/e")
    return httpx.HTTPStatusError(str(status), request=req, response=httpx.Response(status, request=req))


def _orion(by_id):
    """by_id: entity id -> entity dict | Exception; missing id -> 404."""
    async def get_entity(entity_id, options=None):
        item = by_id.get(entity_id)
        if item is None:
            raise _http_error(404)
        if isinstance(item, Exception):
            raise item
        return item

    orion = AsyncMock()
    orion.get_entity = AsyncMock(side_effect=get_entity)
    return orion


TODAY = f"urn:ngsi-ld:CropHealthAssessment:p-1-{NOW:%Y%m%d}"
YDAY = f"urn:ngsi-ld:CropHealthAssessment:p-1-{NOW - timedelta(days=1):%Y%m%d}"


async def _fetch(orion, parcel=PARCEL, tenant="tenant-a"):
    return await fetch_crop_health_state(orion, tenant, parcel, now=NOW)


async def test_fetch_picks_max_observed_at_not_newest_id():
    orion = _orion({
        TODAY: _entity(TODAY, index=0.1, observed="2026-10-22T00:00:05Z"),
        YDAY: _entity(YDAY, index=0.9, observed="2026-10-22T00:00:50Z"),
    })
    st = await _fetch(orion)
    assert st.stress_index == 0.9
    assert st.observed_at == datetime(2026, 10, 22, 0, 0, 50, tzinfo=timezone.utc)
    ids = [c.args[0] for c in orion.get_entity.await_args_list]
    assert ids == [TODAY, YDAY]
    assert all(c.kwargs["options"] == "keyValues" for c in orion.get_entity.await_args_list)


async def test_fetch_today_missing_yesterday_fresh():
    st = await _fetch(_orion({YDAY: _entity(YDAY, index=0.7)}))
    assert st.stress_index == 0.7


async def test_fetch_both_404_is_none_and_cached():
    orion = _orion({})
    assert await _fetch(orion) is None
    assert await _fetch(orion) is None
    assert orion.get_entity.await_count == 2  # one pass (today, yesterday), then cached


async def test_fetch_non_404_error_warns_and_requeries_after_10s(monkeypatch, caplog):
    clock = [1000.0]
    monkeypatch.setattr(wsr, "_monotonic", lambda: clock[0])
    orion = _orion({TODAY: _http_error(503)})
    with caplog.at_level("WARNING"):
        assert await _fetch(orion) is None
    assert any("failed" in r.getMessage() for r in caplog.records)
    n = orion.get_entity.await_count
    clock[0] += 9
    await _fetch(orion)
    assert orion.get_entity.await_count == n
    clock[0] += 2
    await _fetch(orion)
    assert orion.get_entity.await_count > n


async def test_fetch_urn_without_prefix_no_fetch():
    orion = _orion({})
    assert await _fetch(orion, parcel="p-1") is None
    assert await _fetch(orion, parcel="urn:ngsi-ld:AgriParcel:") is None
    orion.get_entity.assert_not_awaited()


async def test_fetch_mismatched_parcel_ignored():
    e = _entity(TODAY)
    e["hasAgriParcel"] = "urn:ngsi-ld:AgriParcel:other"
    assert await _fetch(_orion({TODAY: e})) is None


async def test_fetch_legacy_ref_attribute_and_wrapped_values():
    e = _entity(TODAY)
    del e["hasAgriParcel"]
    e["refAgriParcel"] = {"object": PARCEL}
    e["waterStressIndex"] = {"value": 0.6}
    e["shadeFraction"] = {"value": 0.2}
    e["waterStressFidelity"] = {"value": "iot_sensor"}
    st = await _fetch(_orion({TODAY: e}))
    assert (st.stress_index, st.shade_fraction, st.fidelity) == (0.6, 0.2, "iot_sensor")


async def test_fetch_entities_without_observed_at_rank_last():
    orion = _orion({
        TODAY: _entity(TODAY, index=None, fidelity="unavailable", observed=None),
        YDAY: _entity(YDAY, index=0.3, observed="2026-10-22T01:00:00Z"),
    })
    assert (await _fetch(orion)).stress_index == 0.3


async def test_fetch_keeps_shade_when_fidelity_not_iot():
    st = await _fetch(_orion({TODAY: _entity(TODAY, fidelity="parcel_weather", shade=0.4)}))
    assert st.shade_fraction == 0.4
    assert st.fidelity == "parcel_weather"


async def test_fetch_parses_typed_datetime_and_naive_as_utc():
    for raw, want in (
        ({"@type": "DateTime", "@value": "2026-10-22T11:00:00Z"}, datetime(2026, 10, 22, 11, tzinfo=timezone.utc)),
        ("2026-10-22T11:00:00", datetime(2026, 10, 22, 11, tzinfo=timezone.utc)),
        ("garbage", None),
    ):
        wsr.reset_cache()
        st = await _fetch(_orion({TODAY: _entity(TODAY, observed=raw)}))
        assert st.observed_at == want


@pytest.mark.parametrize("bad", ["x", float("nan"), -0.1, 1.1, True, None])
async def test_fetch_invalid_index_and_shade_become_none(bad):
    st = await _fetch(_orion({TODAY: _entity(TODAY, index=bad, shade=bad)}))
    assert st.stress_index is None
    assert st.shade_fraction is None


async def test_fetch_no_parcel_no_query():
    orion = _orion({})
    assert await _fetch(orion, parcel=None) is None
    orion.get_entity.assert_not_awaited()


async def test_fetch_cache_hits_within_60s(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(wsr, "_monotonic", lambda: clock[0])
    orion = _orion({TODAY: _entity(TODAY)})
    first = await _fetch(orion)
    n = orion.get_entity.await_count
    clock[0] += 59
    assert await _fetch(orion) == first
    assert orion.get_entity.await_count == n
    clock[0] += 2
    await _fetch(orion)
    assert orion.get_entity.await_count > n


async def test_fetch_isolates_tenants():
    orion = _orion({})
    await _fetch(orion)
    n = orion.get_entity.await_count
    await _fetch(orion, tenant="tenant-b")
    assert orion.get_entity.await_count == 2 * n


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [
    "2026-10-22T10:30:00Z",
    {"type": "Property", "value": {"@type": "DateTime", "@value": "2026-10-22T10:30:00+00:00"}},
])
async def test_fetch_reads_shade_observed_at(raw):
    st = await _fetch(_orion({TODAY: _entity(TODAY, shade=0.4, shade_observed=raw, observed=None)}))
    assert st.shade_observed_at == datetime(2026, 10, 22, 10, 30, tzinfo=timezone.utc)
    assert st.observed_at is None


@pytest.mark.asyncio
async def test_fetch_shade_observed_at_absent_is_none():
    st = await _fetch(_orion({TODAY: _entity(TODAY, shade=0.4)}))
    assert st.shade_observed_at is None
