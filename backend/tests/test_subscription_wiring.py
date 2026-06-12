"""Ensure-on-use subscription registration (first SubscriptionRegistrar consumer)."""

import pytest

from tests.conftest import API, TENANT, make_parcel


@pytest.fixture(autouse=True)
def reset_memo():
    from app.services import subscriptions
    subscriptions._ensured.clear()
    yield
    subscriptions._ensured.clear()


@pytest.fixture(autouse=True)
def broker_configured(monkeypatch):
    monkeypatch.setenv("CONTEXT_BROKER_URL", "http://orion-ld-service:1026/ngsi-ld/v1")
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_get_parks_creates_subscriptions_once(client, orion_world):
    client.get(f"{API}/parks")
    assert len(orion_world.created_subscriptions) == 3
    types = {s["entities"][0]["type"] for _, s in orion_world.created_subscriptions}
    assert types == {
        "WeatherObserved", "AgriEnergyTracker",
        "https://saref.etsi.org/saref4agri/PhotovoltaicInstallation"}
    tenants = {t for t, _ in orion_world.created_subscriptions}
    assert tenants == {TENANT}

    # Second call: memoized, no new Orion writes
    client.get(f"{API}/parks")
    assert len(orion_world.created_subscriptions) == 3


def test_existing_subscriptions_deduped_by_description(client, orion_world):
    client.get(f"{API}/parks")
    created_first = len(orion_world.created_subscriptions)
    from app.services import subscriptions
    subscriptions._ensured.clear()  # simulate pod restart
    client.get(f"{API}/parks")
    assert len(orion_world.created_subscriptions) == created_first  # dedup by description


def test_create_park_also_ensures(client, orion_world):
    orion_world.add(make_parcel())
    client.post(f"{API}/parks",
                json={"name": "P", "ref_agri_parcel": "urn:ngsi-ld:AgriParcel:p1"})
    assert len(orion_world.created_subscriptions) == 3


def test_notification_url_in_subscription_body(client, orion_world):
    client.get(f"{API}/parks")
    _, sub = orion_world.created_subscriptions[0]
    assert sub["notification"]["endpoint"]["uri"].endswith("/api/agrienergy/notify")


def test_orion_down_endpoint_still_works(client, orion_world):
    orion_world.fail_all = True
    r = client.get(f"{API}/parks")
    # parks query itself 502s (broker down) but the ensure must not be the cause
    assert r.status_code in (200, 502)
    # and nothing got memoized -> retried next request
    from app.services import subscriptions
    assert subscriptions._ensured == set()
