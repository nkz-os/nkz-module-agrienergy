"""Closed loop /notify: header tenant, SDM extraction, fail-safes, idempotence, MQTT."""

import pytest

from tests.conftest import (
    API, CONST_RULE, PV_TYPE, TENANT, FakeDeviceCommand, FakeIntelligence,
    make_notification, make_parcel, make_tracker,
)

NOTIFY = f"{API}/notify"
T1 = "urn:ngsi-ld:AgriEnergyTracker:t1"


def notify(client, entities, tenant=TENANT):
    headers = {"NGSILD-Tenant": tenant} if tenant else {}
    return client.post(NOTIFY, json=make_notification(entities), headers=headers)


def weather_event(**attrs):
    base = {"id": "urn:ngsi-ld:WeatherObserved:w1", "type": "WeatherObserved"}
    base.update(attrs)
    return base


class TestNotifyAuth:
    def test_no_jwt_needed_tenant_from_header(self, anon_client, orion_world):
        orion_world.add(make_parcel())
        orion_world.add(make_tracker(activeAlgorithm={"type": "Property", "value": CONST_RULE}))
        r = notify(anon_client, [weather_event()])
        assert r.status_code == 200
        assert r.json()["status"] == "processed"

    def test_fiware_service_fallback(self, anon_client, orion_world):
        r = anon_client.post(NOTIFY, json=make_notification([weather_event()]),
                             headers={"Fiware-Service": TENANT})
        assert r.status_code == 200

    def test_missing_tenant_header_400(self, anon_client, orion_world):
        assert notify(anon_client, [weather_event()], tenant=None).status_code == 400

    def test_tenant_header_hyphens_reach_orion_as_is(self, anon_client, orion_world):
        orion_world.add(make_parcel())
        orion_world.add(make_tracker(activeAlgorithm={"type": "Property", "value": CONST_RULE}))
        notify(anon_client, [weather_event()])
        assert orion_world.tenants_seen == {TENANT}  # 'asociacion-allotarra' intact


class TestClosedLoop:
    def _seed(self, orion_world, **tracker_overrides):
        orion_world.add(make_parcel(slope=5.0, aspect=170.0))
        tracker_overrides.setdefault(
            "activeAlgorithm", {"type": "Property", "value": CONST_RULE})
        return orion_world.add(make_tracker(**tracker_overrides))

    def test_weather_event_actuates_tracker(self, anon_client, orion_world):
        self._seed(orion_world)
        r = notify(anon_client, [weather_event()])
        assert r.status_code == 200
        # CONST_RULE with default ghi=800 -> tilt 30 / azimuth 170
        tenant, eid, attrs = orion_world.appended[-1]
        assert (tenant, eid) == (TENANT, T1)
        # Single batched append with the full orientation contract
        assert set(attrs.keys()) == {
            "targetTilt", "targetAzimuth", "tilt", "azimuth", "modelRotation"}
        assert attrs["targetTilt"]["value"] == 30.0
        assert attrs["targetAzimuth"]["value"] == 170.0
        assert attrs["modelRotation"]["value"] == [170.0, -30.0, 0.0]

    def test_idempotence_no_change_no_writes_no_mqtt(self, anon_client, orion_world):
        # Algorithm returns the CURRENT orientation -> loop must converge silently
        rule = {"if": [True, {"tilt": 10, "azimuth": 180}, 0]}
        self._seed(orion_world, activeAlgorithm={"type": "Property", "value": rule},
                   refDevice={"type": "Property", "value": "dev-1"})
        notify(anon_client, [weather_event()])
        assert orion_world.appended == []
        assert FakeDeviceCommand.commands == []

    def test_mqtt_only_with_ref_device(self, anon_client, orion_world):
        self._seed(orion_world)  # no refDevice
        notify(anon_client, [weather_event()])
        assert FakeDeviceCommand.commands == []

    def test_mqtt_sent_with_ref_device(self, anon_client, orion_world):
        self._seed(orion_world, refDevice={"type": "Property", "value": "dev-1"})
        notify(anon_client, [weather_event()])
        assert FakeDeviceCommand.commands == [
            {"tenant": TENANT, "device": "dev-1", "tilt": 30.0, "azimuth": 170.0}]
        # Physical tracker -> TWO appends: intent first, state last
        appends = [a for _, eid, a in orion_world.appended if eid == T1]
        assert len(appends) == 2
        assert set(appends[0].keys()) == {"targetTilt", "targetAzimuth"}
        assert set(appends[-1].keys()) == {"tilt", "azimuth", "modelRotation"}

    def test_direct_tracker_notification(self, anon_client, orion_world):
        tracker = self._seed(orion_world)
        r = notify(anon_client, [tracker])
        assert r.status_code == 200
        assert orion_world.appended  # actuated without a WeatherObserved trigger

    def test_pv_installation_type_processed(self, anon_client, orion_world):
        orion_world.add(make_parcel())
        pv = make_tracker(eid="urn:ngsi-ld:PV:1")
        pv["type"] = PV_TYPE
        pv["activeAlgorithm"] = {"type": "Property", "value": CONST_RULE}
        orion_world.add(pv)
        notify(anon_client, [weather_event()])
        assert any(eid == "urn:ngsi-ld:PV:1" for _, eid, _ in orion_world.appended)

    def test_irrelevant_entity_type_ignored(self, anon_client, orion_world):
        r = notify(anon_client, [{"id": "urn:x", "type": "AgriCrop"}])
        assert r.status_code == 200
        assert orion_world.appended == []

    def test_corrupt_tracker_does_not_abort_batch(self, anon_client, orion_world):
        orion_world.add(make_parcel())
        bad = make_tracker(eid="urn:ngsi-ld:AgriEnergyTracker:bad",
                           location={"type": "GeoProperty", "value": "garbage"})
        orion_world.add(bad)
        good = self._seed(orion_world)
        r = notify(anon_client, [weather_event()])
        assert r.status_code == 200
        assert any(eid == T1 for _, eid, _ in orion_world.appended)  # good one actuated
        assert r.json()["errors"] == 1
        assert r.json()["trackers"] == 1

    def test_rotation_axis_locks_azimuth(self, anon_client, orion_world):
        self._seed(orion_world, rotationAxis={"type": "Property", "value": "north_south"})
        notify(anon_client, [weather_event()])
        _, _, attrs = orion_world.appended[-1]
        assert attrs["targetTilt"]["value"] == 30.0
        assert attrs["targetAzimuth"]["value"] == 180.0  # locked to current

    def test_mqtt_failure_counts_error_and_keeps_twin_truthful(self, anon_client, orion_world):
        FakeDeviceCommand.fail = True
        self._seed(orion_world, refDevice={"type": "Property", "value": "dev-1"})
        r = notify(anon_client, [weather_event()])
        assert r.status_code == 200
        assert r.json()["errors"] == 1
        # Intent recorded, but state NOT updated: the panel did not move.
        assert len(orion_world.appended) == 1
        _, _, attrs = orion_world.appended[0]
        assert set(attrs.keys()) == {"targetTilt", "targetAzimuth"}
        assert FakeDeviceCommand.commands == []

    def test_mqtt_failure_is_retried_on_next_notification(self, anon_client, orion_world):
        FakeDeviceCommand.fail = True
        self._seed(orion_world, refDevice={"type": "Property", "value": "dev-1"})
        notify(anon_client, [weather_event()])
        # Device comes back: tilt still reads the old value, guard lets it retry
        FakeDeviceCommand.fail = False
        r = notify(anon_client, [weather_event()])
        assert r.json()["errors"] == 0
        assert FakeDeviceCommand.commands and FakeDeviceCommand.commands[-1]["tilt"] == 30.0
        # State now updated
        assert any(set(a.keys()) == {"tilt", "azimuth", "modelRotation"}
                   for _, _, a in orion_world.appended)

    def test_azimuth_wraparound_treated_as_unchanged(self, anon_client, orion_world):
        # 359.995 vs 0.0 is 0.005 degrees apart circularly -> no writes
        rule = {"if": [True, {"tilt": 10, "azimuth": 359.995}, 0]}
        self._seed(orion_world, activeAlgorithm={"type": "Property", "value": rule},
                   azimuth={"type": "Property", "value": 0.0})
        notify(anon_client, [weather_event()])
        assert orion_world.appended == []


class TestSDMExtraction:
    def test_panel_dimension_fallback(self, anon_client, orion_world):
        orion_world.add(make_parcel())
        t = make_tracker(activeAlgorithm={"type": "Property", "value": CONST_RULE})
        del t["panelWidth"], t["panelLength"]
        t["panelDimension"] = {"type": "Property", "value": {"width": 3.0, "length": 5.0}}
        orion_world.add(t)
        assert notify(anon_client, [weather_event()]).status_code == 200
        assert orion_world.appended  # processed without panelWidth/panelLength

    def test_model_rotation_orientation_fallback(self, anon_client, orion_world):
        orion_world.add(make_parcel())
        t = make_tracker(activeAlgorithm={"type": "Property", "value": CONST_RULE})
        del t["tilt"], t["azimuth"]
        t["modelRotation"] = {"type": "Property", "value": [170.0, -25.0, 0.0]}
        orion_world.add(t)
        # current tilt derived as -pitch=25 -> CONST_RULE still moves it to 30
        notify(anon_client, [weather_event()])
        assert orion_world.appended[-1][2]["targetTilt"]["value"] == 30.0

    def test_multipoint_location_queries_elevations(self, anon_client, orion_world):
        from tests.conftest import FakeElevation
        FakeElevation.elevations = [100.0, 101.0]
        orion_world.add(make_parcel())
        t = make_tracker(
            activeAlgorithm={"type": "Property", "value": CONST_RULE},
            location={"type": "GeoProperty", "value": {
                "type": "MultiPoint",
                "coordinates": [[-2.0, 43.3], [-2.0001, 43.3]]}},
        )
        orion_world.add(t)
        assert notify(anon_client, [weather_event()]).status_code == 200
        assert orion_world.appended  # array path completed

    def test_missing_parcel_uses_terrain_defaults(self, anon_client, orion_world):
        # parcel NOT seeded -> get_entity 404 -> defaults, no crash
        orion_world.add(make_tracker(
            activeAlgorithm={"type": "Property", "value": CONST_RULE}))
        assert notify(anon_client, [weather_event()]).status_code == 200


class TestBiologyFailSafe:
    def test_intelligence_down_empty_biology(self, anon_client, orion_world):
        FakeIntelligence.response = {}
        rule = {"if": [{">": [{"var": ["biology.stress_index", 0]}, 0.8]},
                       {"tilt": 70, "azimuth": 180}, {"tilt": 30, "azimuth": 170}]}
        orion_world.add(make_parcel())
        orion_world.add(make_tracker(activeAlgorithm={"type": "Property", "value": rule}))
        notify(anon_client, [weather_event()])
        # stress default 0 -> else-branch
        assert orion_world.appended[-1][2]["targetTilt"]["value"] == 30.0

    def test_intelligence_biology_drives_rule(self, anon_client, orion_world):
        FakeIntelligence.response = {"stress_index": 0.95}
        rule = {"if": [{">": [{"var": ["biology.stress_index", 0]}, 0.8]},
                       {"tilt": 70, "azimuth": 180}, {"tilt": 30, "azimuth": 170}]}
        orion_world.add(make_parcel())
        orion_world.add(make_tracker(activeAlgorithm={"type": "Property", "value": rule}))
        notify(anon_client, [weather_event()])
        assert orion_world.appended[-1][2]["targetTilt"]["value"] == 70.0


class TestSignalMapping:
    def test_mapped_sensor_feeds_context(self, anon_client, orion_world):
        orion_world.add(make_parcel())
        orion_world.add({
            "id": "urn:ngsi-ld:AgriSensor:s1", "type": "AgriSensor",
            "leafTemp": {"type": "Property", "value": 1.0},
        })
        rule = {"if": [{"<=": [{"var": ["sensors.leaf_temperature", 10]}, 2]},
                       {"tilt": 0, "azimuth": 180}, {"tilt": 30, "azimuth": 170}]}
        orion_world.add(make_tracker(
            activeAlgorithm={"type": "Property", "value": rule},
            signalMapping={"type": "Property", "value": [
                {"contextKey": "sensors.leaf_temperature",
                 "entityId": "urn:ngsi-ld:AgriSensor:s1", "attribute": "leafTemp"}]},
        ))
        notify(anon_client, [weather_event()])
        # leaf temp 1.0 <= 2 -> frost branch tilt 0
        assert orion_world.appended[-1][2]["targetTilt"]["value"] == 0.0


class TestMagicRadiationDefaults:
    def test_weather_event_without_radiation_uses_documented_defaults(
            self, anon_client, orion_world):
        # SMELL (documented, owner-flagged): WeatherObserved without radiation
        # attrs falls back to ghi=800/dni=600/dhi=200 — the control loop acts on
        # invented irradiance. Follow-up: feed from weather-api instead.
        orion_world.add(make_parcel())
        orion_world.add(make_tracker(
            activeAlgorithm={"type": "Property", "value": CONST_RULE}))
        r = notify(anon_client, [weather_event()])  # no solarRadiation attr
        assert r.status_code == 200
        assert orion_world.appended[-1][2]["targetTilt"]["value"] == 30.0  # ghi=800 path
