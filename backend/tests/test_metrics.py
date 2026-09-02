"""Prometheus metrics for /notify closed-loop."""

from tests.conftest import API, CONST_RULE, make_notification, make_parcel, make_tracker

NOTIFY = f"{API}/notify"


def weather_event(**attrs):
    base = {"id": "urn:ngsi-ld:WeatherObserved:w1", "type": "WeatherObserved"}
    base.update(attrs)
    return base


class TestMetricsEndpoint:
    def test_metrics_exposes_agrienergy_series(self, anon_client):
        r = anon_client.get("/metrics")
        assert r.status_code == 200
        assert "text/plain" in r.headers.get("content-type", "")
        body = r.text
        assert "agrienergy_notify_queue_depth" in body
        assert "agrienergy_tracker_eval_latency_seconds" in body


class TestNotifyQueueDepth:
    def test_queue_depth_returns_to_zero_after_batch(self, anon_client, orion_world):
        orion_world.add(make_parcel())
        orion_world.add(make_tracker(
            activeAlgorithm={"type": "Property", "value": CONST_RULE},
        ))
        r = anon_client.post(
            NOTIFY,
            json=make_notification([weather_event()]),
            headers={"NGSILD-Tenant": "asociacion-allotarra"},
        )
        assert r.status_code == 204
        metrics = anon_client.get("/metrics").text
        assert "agrienergy_notify_queue_depth 0.0" in metrics


class TestTrackerEvalHistogram:
    def test_tracker_eval_records_histogram(self, anon_client, orion_world):
        orion_world.add(make_parcel())
        orion_world.add(make_tracker(
            activeAlgorithm={"type": "Property", "value": CONST_RULE},
        ))
        anon_client.post(
            NOTIFY,
            json=make_notification([weather_event()]),
            headers={"NGSILD-Tenant": "asociacion-allotarra"},
        )
        metrics = anon_client.get("/metrics").text
        assert "agrienergy_tracker_eval_latency_seconds_count" in metrics
        assert "agrienergy_tracker_eval_latency_seconds_bucket" in metrics
