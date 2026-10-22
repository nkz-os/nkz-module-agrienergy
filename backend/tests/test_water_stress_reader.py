"""Tests for the crop-health water stress / shade reader."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

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


def _entity(eid, index=0.5, fidelity="iot_sensor", observed="2026-10-22T11:00:00Z", shade=None):
    e = {"id": eid, "type": "CropHealthAssessment", "hasAgriParcel": PARCEL}
    if index is not None:
        e["waterStressIndex"] = index
    if fidelity is not None:
        e["waterStressFidelity"] = fidelity
    if observed is not None:
        e["waterStressObservedAt"] = observed
    if shade is not None:
        e["shadeFraction"] = shade
    return e


def _orion(entities):
    orion = AsyncMock()
    orion.query_entities = AsyncMock(return_value=entities)
    return orion


async def test_fetch_picks_max_observed_at_not_newest_id():
    orion = _orion([
        _entity("urn:ngsi-ld:CropHealthAssessment:p-1-20261022", index=0.1,
                observed="2026-10-22T00:00:05Z"),
        _entity("urn:ngsi-ld:CropHealthAssessment:p-1-20261021", index=0.9,
                observed="2026-10-22T00:00:50Z"),
    ])
    st = await fetch_crop_health_state(orion, "tenant-a", PARCEL)
    assert st.stress_index == 0.9
    assert st.observed_at == datetime(2026, 10, 22, 0, 0, 50, tzinfo=timezone.utc)
    kwargs = orion.query_entities.await_args.kwargs
    assert kwargs["type"] == "CropHealthAssessment"
    assert kwargs["options"] == "keyValues"
    assert kwargs["limit"] == 10
    assert kwargs["q"] == f'hasAgriParcel=="{PARCEL}"|refAgriParcel=="{PARCEL}"'


async def test_fetch_entities_without_observed_at_rank_last():
    orion = _orion([
        _entity("a", index=None, fidelity="unavailable", observed=None),
        _entity("b", index=0.3, observed="2026-10-22T01:00:00Z"),
    ])
    st = await fetch_crop_health_state(orion, "tenant-a", PARCEL)
    assert st.stress_index == 0.3


async def test_fetch_keeps_shade_when_fidelity_not_iot():
    orion = _orion([_entity("a", fidelity="parcel_weather", shade=0.4)])
    st = await fetch_crop_health_state(orion, "tenant-a", PARCEL)
    assert st.shade_fraction == 0.4
    assert st.fidelity == "parcel_weather"


async def test_fetch_parses_typed_datetime_and_naive_as_utc():
    e = _entity("a", observed={"@type": "DateTime", "@value": "2026-10-22T11:00:00Z"})
    st = await fetch_crop_health_state(_orion([e]), "tenant-a", PARCEL)
    assert st.observed_at == datetime(2026, 10, 22, 11, 0, tzinfo=timezone.utc)
    wsr.reset_cache()
    e = _entity("a", observed="2026-10-22T11:00:00")
    st = await fetch_crop_health_state(_orion([e]), "tenant-a", PARCEL)
    assert st.observed_at == datetime(2026, 10, 22, 11, 0, tzinfo=timezone.utc)
    wsr.reset_cache()
    e = _entity("a", observed="garbage")
    st = await fetch_crop_health_state(_orion([e]), "tenant-a", PARCEL)
    assert st.observed_at is None


@pytest.mark.parametrize("bad", ["x", float("nan"), -0.1, 1.1, True, None])
async def test_fetch_invalid_index_and_shade_become_none(bad):
    e = _entity("a", index=bad, shade=bad)
    st = await fetch_crop_health_state(_orion([e]), "tenant-a", PARCEL)
    assert st.stress_index is None
    assert st.shade_fraction is None


async def test_fetch_empty_result_is_none():
    assert await fetch_crop_health_state(_orion([]), "tenant-a", PARCEL) is None


async def test_fetch_no_parcel_no_query():
    orion = _orion([])
    assert await fetch_crop_health_state(orion, "tenant-a", None) is None
    orion.query_entities.assert_not_awaited()


async def test_fetch_broker_error_returns_none(caplog):
    orion = AsyncMock()
    orion.query_entities = AsyncMock(side_effect=RuntimeError("boom"))
    with caplog.at_level("WARNING"):
        assert await fetch_crop_health_state(orion, "tenant-a", PARCEL) is None
    assert any("boom" in r.getMessage() for r in caplog.records)


async def test_fetch_cache_hits_within_60s(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(wsr, "_monotonic", lambda: clock[0])
    orion = _orion([_entity("a")])
    first = await fetch_crop_health_state(orion, "tenant-a", PARCEL)
    clock[0] += 59
    second = await fetch_crop_health_state(orion, "tenant-a", PARCEL)
    assert first == second
    assert orion.query_entities.await_count == 1
    clock[0] += 2
    await fetch_crop_health_state(orion, "tenant-a", PARCEL)
    assert orion.query_entities.await_count == 2


async def test_fetch_caches_none_and_isolates_tenants():
    orion = _orion([])
    await fetch_crop_health_state(orion, "tenant-a", PARCEL)
    await fetch_crop_health_state(orion, "tenant-a", PARCEL)
    assert orion.query_entities.await_count == 1
    await fetch_crop_health_state(orion, "tenant-b", PARCEL)
    assert orion.query_entities.await_count == 2
