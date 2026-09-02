"""Ack-fast /notify latency smoke — measures HTTP response without background work."""

import time

from fastapi import BackgroundTasks

from tests.conftest import (
    API, CONST_RULE, make_notification, make_parcel, make_tracker,
)

NOTIFY = f"{API}/notify"
ACK_FAST_BUDGET_MS = 250


def weather_event(**attrs):
    base = {"id": "urn:ngsi-ld:WeatherObserved:w1", "type": "WeatherObserved"}
    base.update(attrs)
    return base


def _defer_background(monkeypatch):
    """Prevent TestClient from running background tasks (ack-fast probe)."""
    deferred = []

    def capture_add(self, func, *args, **kwargs):
        deferred.append((func, args, kwargs))

    monkeypatch.setattr(BackgroundTasks, "add_task", capture_add)
    return deferred


class TestNotifyAckLatency:
    def test_fifty_trackers_ack_under_budget(self, anon_client, orion_world, monkeypatch):
        """P0 smoke: Orion webhook ack must not wait for tracker evaluation."""
        _defer_background(monkeypatch)
        orion_world.add(make_parcel())
        for i in range(50):
            orion_world.add(make_tracker(
                eid=f"urn:ngsi-ld:AgriEnergyTracker:t{i}",
                activeAlgorithm={"type": "Property", "value": CONST_RULE},
            ))

        t0 = time.perf_counter()
        r = anon_client.post(
            NOTIFY,
            json=make_notification([weather_event()]),
            headers={"NGSILD-Tenant": "asociacion-allotarra"},
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert r.status_code == 204
        assert r.content == b""
        assert elapsed_ms < ACK_FAST_BUDGET_MS, (
            f"/notify ack took {elapsed_ms:.1f}ms (budget {ACK_FAST_BUDGET_MS}ms)"
        )
