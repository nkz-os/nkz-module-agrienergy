"""Signal mapping resolution and required-signal fail-safe."""

import pytest

from tests.conftest import OrionWorld, FakeOrionClient
from app.services.signal_resolver import (
    forced_stow_orientation,
    parse_signal_mapping,
    resolve_signal_mapping,
)


@pytest.mark.asyncio
async def test_parse_signal_mapping_preserves_required():
    tracker = {
        "signalMapping": {
            "type": "Property",
            "value": [{
                "contextKey": "weather.wind_speed",
                "entityId": "urn:ngsi-ld:WeatherObserved:w1",
                "attribute": "windSpeed",
                "required": True,
            }],
        }
    }
    parsed = parse_signal_mapping(tracker)
    assert parsed[0]["required"] is True


@pytest.mark.asyncio
async def test_required_entity_missing_lists_fault():
    world = OrionWorld()
    orion = FakeOrionClient(world, "tenant-a")
    mapping = [{
        "contextKey": "weather.wind_speed",
        "entityId": "urn:ngsi-ld:WeatherObserved:gone",
        "attribute": "windSpeed",
        "required": True,
    }]
    result = await resolve_signal_mapping(orion, mapping)
    assert result.values == {}
    assert result.missing_required == ["weather.wind_speed"]


@pytest.mark.asyncio
async def test_optional_entity_missing_is_silent():
    world = OrionWorld()
    orion = FakeOrionClient(world, "tenant-a")
    mapping = [{
        "contextKey": "weather.wind_speed",
        "entityId": "urn:ngsi-ld:WeatherObserved:gone",
        "attribute": "windSpeed",
        "required": False,
    }]
    result = await resolve_signal_mapping(orion, mapping)
    assert result.missing_required == []


@pytest.mark.asyncio
async def test_required_attribute_missing_lists_fault():
    world = OrionWorld()
    world.add({
        "id": "urn:ngsi-ld:WeatherObserved:w1",
        "type": "WeatherObserved",
        "temperature": {"type": "Property", "value": 20.0},
    })
    orion = FakeOrionClient(world, "tenant-a")
    mapping = [{
        "contextKey": "weather.wind_speed",
        "entityId": "urn:ngsi-ld:WeatherObserved:w1",
        "attribute": "windSpeed",
        "required": True,
    }]
    result = await resolve_signal_mapping(orion, mapping)
    assert result.missing_required == ["weather.wind_speed"]


def test_forced_stow_keeps_azimuth():
    assert forced_stow_orientation(170.0) == (0.0, 170.0)
