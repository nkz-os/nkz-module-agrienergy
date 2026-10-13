"""
Orion-LD subscription registration via SDK SubscriptionRegistrar.

Converged at startup, periodically and on the install hint
(/internal/lifecycle) onto where the platform says the module is installed
(SDK reconcile_installations): created where enabled, ours removed where not,
nothing touched when the platform cannot answer. The ensure-on-use path stays
as a fallback for a tenant enabled between heal cycles. Idempotent: deterministic ids, and since
SDK 0.8.5 an existing subscription is PATCHed onto the declaration (auth
header, re-armed if Orion paused it).
"""

import asyncio
import logging
import os

from nkz_platform_sdk.notify_auth import derived_tokens_from_env
from nkz_platform_sdk.subscriptions import SubscriptionRegistrar

from app.config import get_settings
from app.services.orion import _strip_ngsi_path

logger = logging.getLogger(__name__)

MODULE_ID = "agrienergy"
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
        # The registrar owns the receiver auth header: the master secret (legacy) or,
        # with NKZ_NOTIFY_DERIVED_TOKENS on, a token bound to the tenant and this
        # receiver so the broker never stores the master.
        internal_secret=internal_service_secret or None,
        derived_tokens=bool(internal_service_secret) and derived_tokens_from_env(),
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


_registrar: SubscriptionRegistrar | None = None


def get_registrar() -> SubscriptionRegistrar:
    """One registrar per process: its lock serializes heal and lifecycle hints."""
    global _registrar
    if _registrar is None:
        _registrar = _build_registrar()
    return _registrar


async def reconcile_once() -> dict | None:
    """One pass over the platform's installs. Never raises; None when it could not run."""
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
    result = await get_registrar().reconcile_installations(MODULE_ID)
    if "skipped" in result:
        logger.warning("Subscription reconcile skipped: %s", result.get("reason"))
        return result
    ensured, removed = result["ensured"], result["removed"]
    if removed["removed"]:
        # A tenant lost its subscriptions: forget what the on-use path memoized,
        # so a later re-enable is ensured again on first use.
        _ensured.clear()
    logger.info(
        "Subscriptions reconciled: created=%d converged=%d removed=%d errors=%d",
        ensured.get("created", 0), ensured.get("converged", 0), removed["removed"],
        len(ensured["errors"]) + len(removed["errors"]),
    )
    for error in ensured["errors"] + removed["errors"]:
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
