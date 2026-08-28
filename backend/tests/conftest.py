"""
Shared fixtures: app client with auth override, in-memory Orion world,
fakes for Intelligence / DeviceCommand / Elevation, NGSI-LD entity factories.

Canonical test tenant is 'asociacion-allotarra' (WITH hyphen): the platform
is hyphen-canonical and any tenant normalization regression must fail loudly.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from app.middleware import TokenPayload, get_current_user

API = "/api/agrienergy"
TENANT = "asociacion-allotarra"
PV_TYPE = "PhotovoltaicInstallation"


# ── Fake Orion (SDK OrionClient surface) ────────────────────────────────────

def _http_error(status: int, eid: str) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", f"http://orion-ld-service:1026/{eid}")
    return httpx.HTTPStatusError(
        str(status), request=req, response=httpx.Response(status, request=req)
    )


class OrionWorld:
    """Scripted entity store + write recorder shared across fake clients."""

    def __init__(self):
        self.entities: dict[str, dict] = {}
        self.appended: list[tuple[str, str, dict]] = []  # (tenant, entity_id, attrs)
        self.created: list[tuple[str, dict]] = []        # (tenant, entity)
        self.subscriptions: list[dict] = []
        self.created_subscriptions: list[tuple[str, dict]] = []
        self.tenants_seen: set[str] = set()
        self.fail_all = False  # simulate Orion down

    def add(self, entity: dict) -> dict:
        self.entities[entity["id"]] = entity
        return entity


class FakeOrionClient:
    """Drop-in for nkz_platform_sdk.orion.OrionClient backed by OrionWorld."""

    def __init__(self, world: OrionWorld, tenant_id: str):
        self.world = world
        self.tenant_id = tenant_id
        world.tenants_seen.add(tenant_id)

    async def query_entities(self, type=None, q=None, limit=100, offset=0, attrs=None):
        if self.world.fail_all:
            raise _http_error(503, "query")
        return [e for e in self.world.entities.values() if e.get("type") == type]

    async def get_entity(self, entity_id: str):
        if self.world.fail_all:
            raise _http_error(503, entity_id)
        ent = self.world.entities.get(entity_id)
        if ent is None:
            raise _http_error(404, entity_id)
        return ent

    async def append_entity_attrs(self, entity_id: str, attrs: dict, overwrite=True):
        if self.world.fail_all:
            raise _http_error(503, entity_id)
        self.world.appended.append((self.tenant_id, entity_id, attrs))
        ent = self.world.entities.setdefault(
            entity_id, {"id": entity_id, "type": "Unknown"}
        )
        ent.update(attrs)

    async def create_entity(self, entity: dict):
        if self.world.fail_all:
            raise _http_error(503, entity.get("id", "?"))
        self.world.created.append((self.tenant_id, entity))
        self.world.entities[entity["id"]] = entity
        return {"id": entity["id"], "status": "created"}

    async def query_subscriptions(self, limit=100):
        if self.world.fail_all:
            raise _http_error(503, "subs")
        return list(self.world.subscriptions)

    async def query_all_subscriptions(self):
        """Mirrors OrionClient: follows Orion's pagination to the end.

        SubscriptionRegistrar switched to this in nkz-platform-sdk 0.8.1 — a
        capped listing made a service unable to find its own subscriptions and
        recreate them every cycle. The fake holds one page, so there is nothing
        to paginate, but it must offer the method or the registrar's dedup
        silently fails open and recreates everything.
        """
        if self.world.fail_all:
            raise _http_error(503, "subs")
        return list(self.world.subscriptions)

    async def create_subscription(self, subscription: dict):
        if self.world.fail_all:
            raise _http_error(503, "subs")
        self.world.subscriptions.append(subscription)
        self.world.created_subscriptions.append((self.tenant_id, subscription))
        return "/ngsi-ld/v1/subscriptions/urn:ngsi-ld:Subscription:test"

    async def close(self):
        pass


# ── Fakes for the other I/O clients ─────────────────────────────────────────

class FakeIntelligence:
    """Configurable evaluate_status; default = service down -> {} (fail-safe)."""

    response: dict = {}
    calls: list = []

    async def evaluate_status(self, **kwargs):
        FakeIntelligence.calls.append(kwargs)
        return dict(FakeIntelligence.response)

    async def evaluate_hydric_stress(self, *a, **kw):
        return 0.0


class FakeDeviceCommand:
    commands: list = []
    fail: bool = False  # simulate MQTT publish failure (client returns False)

    async def send_tracker_command(self, tenant_id, device_id, tilt, azimuth=180.0):
        if FakeDeviceCommand.fail:
            return False
        FakeDeviceCommand.commands.append(
            {"tenant": tenant_id, "device": device_id, "tilt": tilt, "azimuth": azimuth}
        )
        return True


class FakeElevation:
    elevations: list | None = None  # None -> echo zeros

    def __init__(self, tenant_id: str = ""):
        self.tenant_id = tenant_id

    async def get_elevations(self, positions, parcel_id=""):
        if FakeElevation.elevations is not None:
            return list(FakeElevation.elevations)
        return [0.0] * len(positions)


# ── Entity factories ────────────────────────────────────────────────────────

def make_parcel(eid="urn:ngsi-ld:AgriParcel:p1", slope=0.0, aspect=180.0):
    return {
        "id": eid,
        "type": "AgriParcel",
        "name": {"type": "Property", "value": "Parcela test"},
        "slope": {"type": "Property", "value": slope},
        "aspect": {"type": "Property", "value": aspect},
    }


def make_tracker(eid="urn:ngsi-ld:AgriEnergyTracker:t1", **overrides):
    base = {
        "id": eid,
        "type": "AgriEnergyTracker",
        "hasAgriParcel": {"type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:p1"},
        "panelWidth": {"type": "Property", "value": 2.0},
        "panelLength": {"type": "Property", "value": 4.0},
        "clearanceHeight": {"type": "Property", "value": 2.0},
        "NominalPower": {"type": "Property", "value": 1000},
        "tilt": {"type": "Property", "value": 10.0},
        "azimuth": {"type": "Property", "value": 180.0},
        "location": {
            "type": "GeoProperty",
            "value": {"type": "Point", "coordinates": [-2.0, 43.3]},
        },
    }
    base.update(overrides)
    return base


def make_notification(entities: list[dict]) -> dict:
    return {
        "id": "urn:ngsi-ld:Notification:1",
        "type": "Notification",
        "subscriptionId": "urn:ngsi-ld:Subscription:1",
        "notifiedAt": "2026-06-12T12:00:00Z",
        "data": entities,
    }


# A rule with deterministic output regardless of context defaults:
# ghi>10 (default context ghi=800) -> tilt 30 / azimuth 170.
CONST_RULE = {
    "if": [
        {">": [{"var": ["weather.ghi", 0]}, 10]},
        {"tilt": 30, "azimuth": 170},
        {"tilt": -60, "azimuth": 180},
    ]
}


# ── Fixtures ────────────────────────────────────────────────────────────────

def _token(roles: list[str]) -> TokenPayload:
    return TokenPayload(
        {
            "sub": "user-1",
            "email": "tester@example.com",
            "preferred_username": "tester",
            "tenant_id": TENANT,
            "realm_access": {"roles": roles},
        }
    )


@pytest.fixture
def orion_world(monkeypatch):
    """Fake Orion + fakes for every external client. Yields the world."""
    world = OrionWorld()

    def fake_get_orion(tenant_id: str):
        return FakeOrionClient(world, tenant_id)

    # Patch Orion + external clients at every import site used by routes/evaluator.
    monkeypatch.setattr("app.api.get_orion", fake_get_orion)
    monkeypatch.setattr("app.api.deps.get_orion", fake_get_orion)
    monkeypatch.setattr("app.api.notify.get_orion", fake_get_orion)

    import nkz_platform_sdk.subscriptions as sdk_subs
    monkeypatch.setattr(
        sdk_subs, "OrionClient",
        lambda tenant_id, base_url=None, context_url=None: FakeOrionClient(world, tenant_id),
    )
    for target in (
        "app.api.IntelligenceClient",
        "app.api.notify.IntelligenceClient",
        "app.services.tracker_evaluator.IntelligenceClient",
    ):
        monkeypatch.setattr(target, FakeIntelligence)
    for target in (
        "app.api.DeviceCommandClient",
        "app.services.tracker_evaluator.DeviceCommandClient",
    ):
        monkeypatch.setattr(target, FakeDeviceCommand)
    for target in (
        "app.api.ElevationService",
        "app.services.tracker_evaluator.ElevationService",
    ):
        monkeypatch.setattr(target, FakeElevation)
    FakeIntelligence.response = {}
    FakeIntelligence.calls = []
    FakeDeviceCommand.commands = []
    FakeDeviceCommand.fail = False
    FakeElevation.elevations = None
    yield world


@pytest.fixture
def client(orion_world):
    """Authenticated TestClient (regular user, tenant from X-Tenant-ID)."""
    fastapi_app.dependency_overrides[get_current_user] = lambda: _token(["User"])
    with TestClient(fastapi_app) as c:
        c.headers.update({"X-Tenant-ID": TENANT})
        yield c
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def admin_client(orion_world):
    fastapi_app.dependency_overrides[get_current_user] = lambda: _token(["TenantAdmin"])
    with TestClient(fastapi_app) as c:
        c.headers.update({"X-Tenant-ID": TENANT})
        yield c
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def anon_client(orion_world):
    """No auth override, no token: protected routes must 401."""
    with TestClient(fastapi_app) as c:
        yield c
