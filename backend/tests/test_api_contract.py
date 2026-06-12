"""REST contract: auth matrix, tenant priority, parks/status/algorithms/simulate."""

import pytest

from tests.conftest import API, TENANT, make_parcel, make_tracker

PROTECTED_GETS = [
    f"{API}/status?tracker_id=urn:ngsi-ld:AgriEnergyTracker:t1",
    f"{API}/signal-sources",
    f"{API}/parcels",
    f"{API}/parks",
    f"{API}/parks/urn:x/trackers",
    f"{API}/admin/stats",
]


class TestAuthMatrix:
    @pytest.mark.parametrize("path", PROTECTED_GETS)
    def test_protected_routes_401_without_token(self, anon_client, path):
        assert anon_client.get(path).status_code == 401

    def test_protected_post_401(self, anon_client):
        r = anon_client.post(f"{API}/parks", json={"name": "x", "ref_agri_parcel": "urn:p"})
        assert r.status_code == 401

    def test_admin_stats_403_for_regular_user(self, client):
        assert client.get(f"{API}/admin/stats").status_code == 403

    def test_admin_stats_200_for_tenant_admin(self, admin_client):
        r = admin_client.get(f"{API}/admin/stats")
        assert r.status_code == 200
        assert r.json()["user"] == "tester@example.com"

    def test_simulate_needs_no_token(self, anon_client):
        # Pinned: /simulate is tenant-agnostic compute; public access is fronted
        # by api-gateway JWT. Changing this is an owner decision.
        payload = {
            "tracker": {"id": "t", "panel_width": 2, "panel_length": 4,
                        "capacity_w": 1000, "min_tilt": -60, "max_tilt": 60,
                        "lat": 43.3, "lon": -2.0, "parent_parcel_id": "p"},
            "parcel": {"id": "p", "slope": 0, "aspect": 180},
            "telemetry": {"timestamp": "2026-06-21T12:00:00Z", "ghi": 800,
                          "dni": 700, "dhi": 120, "actual_tilt": 0,
                          "actual_azimuth": 180},
            "target_tilt": 30,
        }
        assert anon_client.post(f"{API}/simulate", json=payload).status_code == 200


class TestTenantPriority:
    def test_x_tenant_id_beats_claim(self, client, orion_world):
        client.get(f"{API}/parks", headers={"X-Tenant-ID": "other-tenant"})
        assert "other-tenant" in orion_world.tenants_seen

    def test_claim_used_without_headers(self, client, orion_world):
        # client fixture sets X-Tenant-ID; blank it so the JWT claim is used
        client.get(f"{API}/parks", headers={"X-Tenant-ID": ""})
        assert TENANT in orion_world.tenants_seen


class TestAlgorithmsEndpoint:
    def test_lists_seven_presets(self, client):
        algos = client.get(f"{API}/algorithms").json()["algorithms"]
        assert len(algos) == 7
        assert all({"id", "name", "logic"} <= set(a.keys()) for a in algos)


class TestParks:
    def test_create_park_writes_orion_with_hyphen_tenant(self, client, orion_world):
        orion_world.add(make_parcel())
        r = client.post(f"{API}/parks",
                        json={"name": "Parque 1", "ref_agri_parcel": "urn:ngsi-ld:AgriParcel:p1"})
        assert r.status_code == 201
        tenant, entity = orion_world.created[0]
        assert tenant == TENANT  # hyphens intact — THE regression test
        assert entity["type"] == "AgriSolarPark"
        assert entity["hasAgriParcel"]["object"] == "urn:ngsi-ld:AgriParcel:p1"

    def test_create_park_orion_down_502(self, client, orion_world):
        orion_world.fail_all = True
        r = client.post(f"{API}/parks",
                        json={"name": "x", "ref_agri_parcel": "urn:p"})
        assert r.status_code == 502

    def test_list_parks_with_tracker_counts(self, client, orion_world):
        orion_world.add(make_parcel())
        orion_world.add({
            "id": "urn:ngsi-ld:AgriSolarPark:park1", "type": "AgriSolarPark",
            "name": {"type": "Property", "value": "P1"},
            "hasAgriParcel": {"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:p1"},
        })
        orion_world.add(make_tracker())
        parks = client.get(f"{API}/parks").json()["parks"]
        assert len(parks) == 1
        assert parks[0]["tracker_count"] == 1
        assert parks[0]["tracker_ids"] == ["urn:ngsi-ld:AgriEnergyTracker:t1"]

    def test_park_trackers_404_unknown_park(self, client, orion_world):
        assert client.get(f"{API}/parks/urn:nope/trackers").status_code == 404


class TestTrackerStatus:
    def test_status_404_unknown_tracker(self, client, orion_world):
        r = client.get(f"{API}/status", params={"tracker_id": "urn:nope"})
        assert r.status_code == 404

    def test_status_reads_orientation(self, client, orion_world):
        orion_world.add(make_tracker(tilt={"type": "Property", "value": 42.0}))
        r = client.get(f"{API}/status",
                       params={"tracker_id": "urn:ngsi-ld:AgriEnergyTracker:t1"})
        assert r.status_code == 200
        assert r.json()["orientation"]["tilt"] == 42.0


class TestTrackerPatches:
    def test_algorithm_preset_resolved_and_appended(self, client, orion_world):
        orion_world.add(make_tracker())
        r = client.patch(f"{API}/trackers/urn:ngsi-ld:AgriEnergyTracker:t1/algorithm",
                         json={"activeAlgorithm": {"id": "wind_barrier"}})
        assert r.status_code == 200
        tenant, eid, attrs = orion_world.appended[-1]
        assert tenant == TENANT
        assert "activeAlgorithm" in attrs
        assert attrs["activeAlgorithm"]["value"]["if"]  # resolved logic, not the id

    def test_algorithm_unknown_preset_400(self, client, orion_world):
        orion_world.add(make_tracker())
        r = client.patch(f"{API}/trackers/urn:ngsi-ld:AgriEnergyTracker:t1/algorithm",
                         json={"activeAlgorithm": {"id": "nope"}})
        assert r.status_code == 400

    def test_signal_mapping_appended(self, client, orion_world):
        orion_world.add(make_tracker())
        body = {"signalMapping": [
            {"contextKey": "weather.ghi",
             "entityId": "urn:ngsi-ld:WeatherObserved:w1", "attribute": "solarRadiation"}
        ]}
        r = client.patch(
            f"{API}/trackers/urn:ngsi-ld:AgriEnergyTracker:t1/signal-mapping", json=body)
        assert r.status_code == 200
        _, _, attrs = orion_world.appended[-1]
        assert attrs["signalMapping"]["value"][0]["contextKey"] == "weather.ghi"

    def test_patch_orion_down_502(self, client, orion_world):
        orion_world.fail_all = True
        r = client.patch(f"{API}/trackers/urn:x/algorithm",
                         json={"activeAlgorithm": {"id": "wind_barrier"}})
        assert r.status_code == 502
