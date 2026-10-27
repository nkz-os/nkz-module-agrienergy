"""
AgriEnergy Orchestrator Backend - Authentication

User routes trust the identity the api-gateway forwards after validating the JWT
(X-Tenant-ID, X-User-ID, X-User-Roles) and check its HMAC signature
(X-Auth-Signature) with ``require_auth`` from the SDK, so a pod inside the
cluster cannot claim another tenant. The module never validates JWTs itself.
"""

import logging
from typing import Optional

from fastapi import Header, HTTPException, status
from nkz_platform_sdk import auth as sdk_auth
from nkz_platform_sdk.auth import AuthContext, require_auth

logger = logging.getLogger(__name__)


def require_roles(*required_roles: str):
    """Dependency (already wrapped in Depends) that requires one of the given roles; 403 otherwise."""
    return require_auth(roles=list(required_roles))


def ensure_signature_enforced() -> None:
    """Refuse to start when gateway signatures would not be checked.

    Without REQUIRE_HMAC_SIGNATURE=true and HMAC_SECRET, require_auth accepts
    unsigned identity headers: that is fail-open, so the service must not run.
    """
    if not (sdk_auth.REQUIRE_HMAC and sdk_auth.HMAC_SECRET):
        logger.critical(
            "gateway signature check disabled: REQUIRE_HMAC_SIGNATURE=%s HMAC_SECRET set=%s",
            sdk_auth.REQUIRE_HMAC,
            bool(sdk_auth.HMAC_SECRET),
        )
        raise RuntimeError("REQUIRE_HMAC_SIGNATURE=true and HMAC_SECRET are required")


def get_notification_tenant(
    ngsild_tenant: Optional[str] = Header(None, alias="NGSILD-Tenant"),
    fiware_service: Optional[str] = Header(None, alias="Fiware-Service"),
) -> str:
    """Tenant for Orion-LD notification webhooks (platform pattern: telemetry-worker).

    Orion-LD sends NGSILD-Tenant (and legacy Fiware-Service) but no JWT —
    notifications are cluster-internal; public traffic is fronted by api-gateway.
    """
    tenant = ngsild_tenant or fiware_service
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing NGSILD-Tenant header",
        )
    return tenant


def get_tenant_id(ctx: AuthContext = require_auth()) -> str:
    """Tenant of the signed gateway identity."""
    return ctx.tenant_id
