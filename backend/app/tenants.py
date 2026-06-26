"""Tenant discovery for AgriEnergy scheduled jobs (mirrors weather-map pattern)."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _postgres_url() -> str:
    url = os.getenv("POSTGRES_URL", "").strip()
    if url:
        return url
    host = os.getenv("POSTGRES_HOST", "postgresql-service")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "nekazari")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    if not password:
        return ""
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _discover_from_db() -> list[str]:
    url = _postgres_url()
    if not url:
        logger.warning("tenants: no POSTGRES credentials — cannot discover tenants")
        return []
    try:
        import psycopg2

        conn = psycopg2.connect(url)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT tenant_id FROM tenant_installed_modules "
                "WHERE module_id = 'agrienergy' "
                "AND tenant_id IS NOT NULL AND tenant_id != '' "
                "AND tenant_id <> 'platform' "
                "ORDER BY tenant_id"
            )
            rows = [r[0] for r in cur.fetchall()]
            cur.close()
            return rows
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("tenants: DB discovery failed: %s", exc)
        return []


def discover_tenants(env_override_var: str = "AGGREGATION_TENANTS") -> list[str]:
    """Active tenants for daily aggregation cron.

    1. Env override (comma-separated).
    2. ``tenant_installed_modules`` where module_id = agrienergy.
    3. Empty — skip run (never ``default``).
    """
    override = os.getenv(env_override_var, "").strip()
    if override:
        return [t.strip() for t in override.split(",") if t.strip()]
    found = _discover_from_db()
    if found:
        logger.info("tenants: discovered %d agrienergy tenants: %s", len(found), found)
        return found
    logger.warning("tenants: none discovered — skipping aggregation run")
    return []
