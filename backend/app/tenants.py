"""Tenant discovery for AgriEnergy scheduled jobs.

Where agrienergy is installed comes from the platform (entity-manager, SDK
``installed_tenants``), so the module holds no database credential.
"""

from __future__ import annotations

import logging
import os

from nkz_platform_sdk.installations import InstalledTenantsUnavailable, installed_tenants

logger = logging.getLogger(__name__)

MODULE_ID = "agrienergy"


async def discover_tenants(env_override_var: str = "AGGREGATION_TENANTS") -> list[str]:
    """Tenants for the daily aggregation cron.

    1. Env override (comma-separated).
    2. Tenants where the platform says agrienergy is installed and enabled.
    3. Empty — skip the run (never ``default``), also when the platform
       cannot answer: a missed day is recomputed, a guessed tenant is not.
    """
    override = os.getenv(env_override_var, "").strip()
    if override:
        return [t.strip() for t in override.split(",") if t.strip()]
    try:
        installs = await installed_tenants(MODULE_ID)
    except InstalledTenantsUnavailable as exc:
        logger.warning("tenants: platform did not answer, skipping run: %s", exc)
        return []
    found = [t for t in installs.enabled if t != "platform"]
    if found:
        logger.info("tenants: discovered %d agrienergy tenants: %s", len(found), found)
        return found
    logger.warning("tenants: none discovered — skipping aggregation run")
    return []
