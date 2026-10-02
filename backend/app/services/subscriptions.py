"""
Orion-LD subscription registration via SDK SubscriptionRegistrar.

Registered at startup and re-converged periodically for every tenant with the
module installed and enabled, so a tenant's subscriptions exist before anyone
opens the parks screens. The ensure-on-use path stays as a fallback for a
tenant enabled between heal cycles. Idempotent: deterministic ids, and since
SDK 0.8.5 an existing subscription is PATCHed onto the declaration (auth
header, re-armed if Orion paused it).
"""

import asyncio
import logging
import os

from nkz_platform_sdk.subscriptions import SubscriptionRegistrar

from app.config import get_settings
from app.services.orion import _strip_ngsi_path
from app.tenants import installed_tenants

logger = logging.getLogger(__name__)

PV_TYPE = "PhotovoltaicInstallation"
_ensured: set[str] = set()


def _build_registrar() -> SubscriptionRegistrar:
    settings = get_settings()
    internal_service_secret = os.getenv("INTERNAL_SERVICE_SECRET", "")
    return SubscriptionRegistrar(
        orion_url=_strip_ngsi_path(settings.context_broker_url),
        notification_url=settings.notification_url,
        subscriptions=[
            {"type": "WeatherObserved", "throttling": 60},
            {"type": "AgriEnergyTracker", "throttling": 30},
            {"type": PV_TYPE, "throttling": 30},
        ],
        module_name="agrienergy",
        notification_headers=(
            {"X-Internal-Service-Secret": internal_service_secret}
            if internal_service_secret else None
        ),
    )


async def ensure_subscriptions(tenant_id: str) -> None:
    """Idempotent, fail-safe: a broker error must never break the calling endpoint."""
    if not tenant_id or tenant_id in _ensured:
        return
    settings = get_settings()
    if not settings.context_broker_url:
        return
    try:
        result = await _build_registrar().ensure_all([tenant_id])
        if result.get("errors"):
            logger.warning("ensure_subscriptions partial for %s: %s",
                           tenant_id, result["errors"])
            return  # not memoized -> retried on next request
        _ensured.add(tenant_id)
        logger.info("Subscriptions ensured for tenant %s (created=%d skipped=%d)",
                    tenant_id, result.get("created", 0), result.get("skipped", 0))
    except Exception as e:
        logger.warning("ensure_subscriptions failed for %s: %s", tenant_id, e)


async def _installed_tenants() -> list[str]:
    return await asyncio.to_thread(installed_tenants)


async def reconcile_once() -> dict | None:
    """One pass over installed tenants. Never raises; None when it could not run."""
    settings = get_settings()
    if not settings.context_broker_url:
        logger.error("CONTEXT_BROKER_URL not set — Orion subscriptions NOT registered")
        return None
    if not os.getenv("INTERNAL_SERVICE_SECRET", ""):
        logger.error(
            "INTERNAL_SERVICE_SECRET not set — Orion subscriptions NOT registered; "
            "/notify would reject every notification"
        )
        return None
    try:
        tenants = await _installed_tenants()
    except Exception as e:  # noqa: BLE001 — a DB outage must not kill the service
        logger.warning("Subscription reconcile skipped, tenant lookup failed: %s", e)
        return None
    result = await _build_registrar().ensure_all(tenants)
    if not result.get("errors"):
        _ensured.update(tenants)
    logger.info(
        "Subscriptions reconciled for %s: created=%d converged=%d errors=%d",
        tenants, result.get("created", 0), result.get("converged", 0),
        len(result.get("errors", [])),
    )
    for error in result.get("errors", []):
        logger.warning("Subscription reconcile error: %s", error)
    return result


async def run_subscription_reconciler(interval_minutes: int) -> None:
    """Reconcile now, then every `interval_minutes`. Never raises (until cancelled)."""
    while True:
        try:
            await reconcile_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("Subscription reconcile failed: %s", e)
        await asyncio.sleep(interval_minutes * 60)
