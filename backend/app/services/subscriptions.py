"""
Ensure-on-use Orion-LD subscription registration via SDK SubscriptionRegistrar.

The module has no tenant enumeration source (no PG), so subscriptions are
ensured the first time each tenant touches the parks endpoints in this
process. Idempotent across pods/restarts: the registrar dedups by
subscription description in Orion.
"""

import logging

from nkz_platform_sdk.subscriptions import SubscriptionRegistrar

from app.config import get_settings
from app.services.orion import _strip_ngsi_path

logger = logging.getLogger(__name__)

PV_TYPE = "PhotovoltaicInstallation"
_ensured: set[str] = set()


def _build_registrar() -> SubscriptionRegistrar:
    settings = get_settings()
    return SubscriptionRegistrar(
        orion_url=_strip_ngsi_path(settings.context_broker_url),
        notification_url=settings.notification_url,
        subscriptions=[
            {"type": "WeatherObserved", "throttling": 60},
            {"type": "AgriEnergyTracker", "throttling": 30},
            {"type": PV_TYPE, "throttling": 30},
        ],
        module_name="agrienergy",
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
