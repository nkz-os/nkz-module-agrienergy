"""Adapter contract: tenant as-is, base_url strip, NGSI-LD fragment helpers."""

import httpx
import pytest

from app.services.orion import (
    _strip_ngsi_path, get_entity_or_none, get_orion, prop, rel,
)


class TestStripNgsiPath:
    @pytest.mark.parametrize("raw,expected", [
        ("http://orion-ld-service:1026/ngsi-ld/v1", "http://orion-ld-service:1026"),
        ("http://orion-ld-service:1026/ngsi-ld/v1/", "http://orion-ld-service:1026"),
        ("http://orion-ld-service:1026", "http://orion-ld-service:1026"),
        ("", ""),
    ])
    def test_strip(self, raw, expected):
        assert _strip_ngsi_path(raw) == expected


class TestGetOrion:
    def test_tenant_passed_as_is_hyphen_canonical(self):
        client = get_orion("asociacion-allotarra")
        # THE bug this migration kills: never lowercase/underscore-normalize
        assert client.tenant_id == "asociacion-allotarra"
        headers = client._headers("application/json")
        assert headers["NGSILD-Tenant"] == "asociacion-allotarra"
        assert headers["Fiware-Service"] == "asociacion-allotarra"

    def test_base_url_stripped_from_settings(self, monkeypatch):
        from app.config import get_settings
        get_settings.cache_clear()
        monkeypatch.setenv("CONTEXT_BROKER_URL", "http://orion-ld-service:1026/ngsi-ld/v1")
        try:
            client = get_orion("montiko")
            assert client.base_url == "http://orion-ld-service:1026"
            assert client._url("/ngsi-ld/v1/entities").endswith("1026/ngsi-ld/v1/entities")
        finally:
            get_settings.cache_clear()


class TestFragmentHelpers:
    def test_prop(self):
        assert prop(30.0) == {"type": "Property", "value": 30.0}
        assert prop([1, 2, 3]) == {"type": "Property", "value": [1, 2, 3]}

    def test_rel(self):
        assert rel("urn:ngsi-ld:AgriParcel:p1") == {
            "type": "Relationship", "object": "urn:ngsi-ld:AgriParcel:p1"
        }


class TestGetEntityOrNone:
    class _Fake:
        def __init__(self, status):
            self.status = status

        async def get_entity(self, eid):
            req = httpx.Request("GET", "http://x")
            if self.status != 200:
                raise httpx.HTTPStatusError(
                    "err", request=req,
                    response=httpx.Response(self.status, request=req),
                )
            return {"id": eid}

    @pytest.mark.asyncio
    async def test_found(self):
        assert (await get_entity_or_none(self._Fake(200), "urn:x"))["id"] == "urn:x"

    @pytest.mark.asyncio
    async def test_404_returns_none(self):
        assert await get_entity_or_none(self._Fake(404), "urn:x") is None

    @pytest.mark.asyncio
    async def test_other_errors_propagate(self):
        with pytest.raises(httpx.HTTPStatusError):
            await get_entity_or_none(self._Fake(503), "urn:x")
