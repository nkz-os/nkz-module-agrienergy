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


def _installs(monkeypatch, enabled=(), disabled=(), not_installed=()):
    """Where the platform says agrienergy is installed (SDK installed_tenants)."""
    import nkz_platform_sdk.subscriptions as sdk_subs
    from nkz_platform_sdk.installations import TenantInstallations

    async def fake(module_id, **kwargs):
        assert module_id == "agrienergy"
        return TenantInstallations(module_id, tuple(enabled), tuple(disabled), tuple(not_installed))

    monkeypatch.setattr(sdk_subs, "installed_tenants", fake)
    monkeypatch.setattr("app.tenants.installed_tenants", fake)


def _platform_down(monkeypatch):
    import nkz_platform_sdk.subscriptions as sdk_subs
    from nkz_platform_sdk.installations import InstalledTenantsUnavailable

    async def fake(module_id, **kwargs):
        raise InstalledTenantsUnavailable("entity-manager answered 503")

    monkeypatch.setattr(sdk_subs, "installed_tenants", fake)
    monkeypatch.setattr("app.tenants.installed_tenants", fake)


async def test_registers_all_types_for_installed_tenants(orion_world, monkeypatch):
    _installs(monkeypatch, enabled=["tenant-a"])

    result = await subscriptions.reconcile_once()

    assert result["ensured"]["created"] == 3 and result["ensured"]["errors"] == []
    assert {t for t, _ in orion_world.created_subscriptions} == {"tenant-a"}
    assert {s["entities"][0]["type"] for _, s in orion_world.created_subscriptions} == TYPES
    for _, sub in orion_world.created_subscriptions:
        assert sub["notification"]["endpoint"]["receiverInfo"] == [
            {"key": "X-Internal-Service-Secret", "value": SECRET}
        ]


async def test_existing_paused_subscription_is_patched_and_rearmed(orion_world, monkeypatch):
    _installs(monkeypatch, enabled=["tenant-a"])
    stale = {
        "id": "urn:ngsi-ld:Subscription:agrienergy:WeatherObserved",
        "type": "Subscription",
        "isActive": False,
        "notification": {"endpoint": {"uri": "http://old", "accept": "application/json"}},
    }
    orion_world.subscriptions.append(stale)

    result = await subscriptions.reconcile_once()

    assert result["ensured"]["converged"] == 1 and result["ensured"]["errors"] == []
    assert stale["isActive"] is True
    assert stale["notification"]["endpoint"]["receiverInfo"] == [
        {"key": "X-Internal-Service-Secret", "value": SECRET}
    ]


async def test_no_secret_registers_nothing(orion_world, monkeypatch):
    monkeypatch.delenv("INTERNAL_SERVICE_SECRET")
    _installs(monkeypatch, enabled=["tenant-a"])

    assert await subscriptions.reconcile_once() is None
    assert orion_world.created_subscriptions == []


async def test_platform_unavailable_touches_nothing(orion_world, monkeypatch):
    _platform_down(monkeypatch)
    orion_world.subscriptions.append(
        {"id": "urn:ngsi-ld:Subscription:agrienergy:WeatherObserved", "type": "Subscription"})

    result = await subscriptions.reconcile_once()

    assert result["skipped"] == "unavailable"
    assert orion_world.created_subscriptions == [] and orion_world.deleted_subscriptions == []


async def test_disabled_tenant_loses_these_subscriptions(orion_world, monkeypatch):
    _installs(monkeypatch, disabled=["tenant-b"])
    orion_world.subscriptions.append(
        {"id": "urn:ngsi-ld:Subscription:agrienergy:WeatherObserved", "type": "Subscription"})
    subscriptions._ensured.add("tenant-b")

    result = await subscriptions.reconcile_once()

    assert result["removed"]["removed"] == 1
    assert orion_world.deleted_subscriptions == [
        ("tenant-b", "urn:ngsi-ld:Subscription:agrienergy:WeatherObserved")]
    assert "tenant-b" not in subscriptions._ensured  # on-use path re-ensures after re-enable


async def test_aggregation_tenants_come_from_the_platform(monkeypatch):
    from app.tenants import discover_tenants

    monkeypatch.delenv("AGGREGATION_TENANTS", raising=False)
    _installs(monkeypatch, enabled=["tenant-a", "platform"], disabled=["tenant-b"])
    assert await discover_tenants() == ["tenant-a"]


async def test_aggregation_skips_when_platform_unavailable(monkeypatch):
    from app.tenants import discover_tenants

    monkeypatch.delenv("AGGREGATION_TENANTS", raising=False)
    _platform_down(monkeypatch)
    assert await discover_tenants() == []


async def test_aggregation_env_override(monkeypatch):
    from app.tenants import discover_tenants

    monkeypatch.setenv("AGGREGATION_TENANTS", "x, y")
    assert await discover_tenants() == ["x", "y"]


def test_no_database_read_left():
    import inspect

    import app.services.subscriptions as subs
    import app.tenants as tenants

    for mod in (subs, tenants):
        assert "tenant_installed_modules" not in inspect.getsource(mod)


def test_lifecycle_hint_route_requires_auth():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    assert client.post("/api/agrienergy/internal/lifecycle").status_code == 401
    r = client.post("/api/agrienergy/internal/lifecycle",
                    headers={"X-Internal-Service-Secret": SECRET})
    assert r.status_code == 202
