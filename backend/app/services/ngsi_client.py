import httpx
import logging
import re
import os
from typing import Dict, Any, List
from app.config import get_settings

logger = logging.getLogger(__name__)


def _make_headers(tenant_id: str) -> dict:
    """Build canonical NGSI-LD headers with tenant normalization.

    Applies FIWARE multi-tenant conventions: lowercase, underscores,
    alphanumeric-only normalized tenant value for both NGSILD-Tenant
    and Fiware-Service headers.
    """
    n = tenant_id.lower().strip().replace('-', '_').replace(' ', '_')
    n = re.sub(r'[^a-z0-9_]', '', n)
    n = n.strip('_') or tenant_id
    headers = {
        "NGSILD-Tenant": n,
        "Fiware-Service": n,
        "Fiware-ServicePath": "/",
        "Accept": "application/ld+json",
    }
    ctx = os.getenv("CONTEXT_URL", "")
    if ctx:
        headers["Link"] = (
            f'<{ctx}>; '
            f'rel="http://www.w3.org/ns/json-ld#context"; '
            f'type="application/ld+json"'
        )
    return headers


class ContextBrokerClient:
    """
    Client for NGSI-LD queries against Orion-LD (directly, no entity-manager middleman).
    Uses CONTEXT_BROKER_URL env var (e.g. http://orion-ld-service:1026/ngsi-ld/v1).
    """

    def __init__(self):
        self.settings = get_settings()
        # Orion-LD direct URL (set via CONTEXT_BROKER_URL env var in K8s)
        self.base_url = (self.settings.context_broker_url or "http://orion-ld-service:1026/ngsi-ld/v1").rstrip("/")

    def _headers(self, tenant_id: str, content_type: str | None = None) -> dict:
        """Build headers for Orion-LD multi-tenant queries.

        Delegates to module-level _make_headers for canonical tenant
        normalization and FIWARE multi-tenant headers, then overrides
        Content-Type when supplied.
        """
        h = _make_headers(tenant_id)
        if content_type:
            h["Content-Type"] = content_type
        return h

    async def get_entities_by_type(self, tenant_id: str, entity_type: str) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/entities",
                    params={"type": entity_type, "limit": 500},
                    headers=self._headers(tenant_id),
                )
                response.raise_for_status()
                data = response.json()
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error("Error fetching entities type=%s: %s", entity_type, e)
            return []

    async def get_entity(self, tenant_id: str, entity_id: str) -> Dict[str, Any] | None:
        """Fetch a single entity by id. Returns None if not found or on error."""
        import urllib.parse
        try:
            encoded_id = urllib.parse.quote(entity_id, safe="")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/entities/{encoded_id}",
                    headers=self._headers(tenant_id),
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("Error fetching entity %s: %s", entity_id, e)
            return None

    async def update_entity_attribute(self, tenant_id: str, entity_id: str, attr_name: str, value: Any) -> bool:
        import urllib.parse
        payload = {
            attr_name: {
                "type": "Property",
                "value": value,
            }
        }
        try:
            encoded_id = urllib.parse.quote(entity_id, safe="")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/entities/{encoded_id}/attrs",
                    json=payload,
                    headers=self._headers(tenant_id, "application/json"),
                )
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error("Error updating entity %s attr %s: %s", entity_id, attr_name, e)
            return False

    async def create_entity(self, tenant_id: str, entity: dict) -> bool:
        """
        Create an NGSI-LD entity in Orion (POST /ngsi-ld/v1/entities).
        Returns True on 201/200.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/entities",
                    json=entity,
                    headers=self._headers(tenant_id, "application/ld+json" if "@context" in entity else "application/json"),
                )
                if response.status_code in (200, 201):
                    return True
                logger.error(
                    "Create entity failed: %s %s",
                    response.status_code,
                    response.text[:200],
                )
                return False
        except Exception as e:
            logger.error("Error creating entity: %s", e)
            return False
