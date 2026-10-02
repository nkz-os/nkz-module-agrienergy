"""Subscriptions are registered for installed tenants at startup, not on first use.

Regression: registration only happened when someone opened the parks screens, so a
tenant with the module enabled had no subscriptions at all and the closed loop
(weather -> tracker -> actuator) never received a notification.
"""

import pytest

from app.services import subscriptions

SECRET = "test-internal-secret"
TYPES = {"WeatherObserved", "AgriEnergyTracker", "PhotovoltaicInstallation"}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("CONTEXT_BROKER_URL", "http://orion-ld-service:1026/ngsi-ld/v1")
    monkeypatch.setenv("INTERNAL_SERVICE_SECRET", SECRET)
    from app.config import get_settings
    get_settings.cache_clear()
    subscriptions._ensured.clear()
    yield
    get_settings.cache_clear()
    subscriptions._ensured.clear()


def _tenants(*ids):
    async def provider():
        return list(ids)
    return provider


async def test_registers_all_types_for_installed_tenants(orion_world, monkeypatch):
    monkeypatch.setattr(subscriptions, "_installed_tenants", _tenants("tenant-a"))

    result = await subscriptions.reconcile_once()

    assert result["created"] == 3 and result["errors"] == []
    assert {t for t, _ in orion_world.created_subscriptions} == {"tenant-a"}
    assert {s["entities"][0]["type"] for _, s in orion_world.created_subscriptions} == TYPES
    for _, sub in orion_world.created_subscriptions:
        assert sub["notification"]["endpoint"]["receiverInfo"] == [
            {"key": "X-Internal-Service-Secret", "value": SECRET}
        ]
    assert subscriptions._ensured == {"tenant-a"}


async def test_existing_paused_subscription_is_patched_and_rearmed(orion_world, monkeypatch):
    monkeypatch.setattr(subscriptions, "_installed_tenants", _tenants("tenant-a"))
    stale = {
        "id": "urn:ngsi-ld:Subscription:agrienergy:WeatherObserved",
        "type": "Subscription",
        "isActive": False,
        "notification": {"endpoint": {"uri": "http://old", "accept": "application/json"}},
    }
    orion_world.subscriptions.append(stale)

    result = await subscriptions.reconcile_once()

    assert result["converged"] == 1 and result["errors"] == []
    assert stale["isActive"] is True
    assert stale["notification"]["endpoint"]["receiverInfo"] == [
        {"key": "X-Internal-Service-Secret", "value": SECRET}
    ]


async def test_no_secret_registers_nothing(orion_world, monkeypatch):
    monkeypatch.delenv("INTERNAL_SERVICE_SECRET")
    monkeypatch.setattr(subscriptions, "_installed_tenants", _tenants("tenant-a"))

    assert await subscriptions.reconcile_once() is None
    assert orion_world.created_subscriptions == []


async def test_tenant_lookup_failure_touches_nothing(orion_world, monkeypatch):
    async def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(subscriptions, "_installed_tenants", boom)

    assert await subscriptions.reconcile_once() is None
    assert orion_world.created_subscriptions == []


def test_installed_tenants_only_enabled_installs_of_agrienergy(monkeypatch):
    seen = {}

    class Cur:
        def execute(self, sql):
            seen["sql"] = sql

        def fetchall(self):
            return [("tenant-a",)]

        def close(self):
            pass

    class Conn:
        def cursor(self):
            return Cur()

        def close(self):
            seen["closed"] = True

    import psycopg2

    monkeypatch.setenv("POSTGRES_URL", "postgresql://u@db/x")
    monkeypatch.setattr(psycopg2, "connect", lambda url: Conn())
    from app.tenants import installed_tenants

    assert installed_tenants() == ["tenant-a"]
    assert "module_id = 'agrienergy'" in seen["sql"]
    assert "is_enabled" in seen["sql"]
    assert seen["closed"]


def test_installed_tenants_without_credentials_raises(monkeypatch):
    for var in ("POSTGRES_URL", "POSTGRES_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    from app.tenants import installed_tenants

    with pytest.raises(RuntimeError):
        installed_tenants()
