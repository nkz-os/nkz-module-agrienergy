"""CLI entrypoint for K8s CronJob — daily Wh aggregation."""

from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    from app.services.daily_aggregation import run_daily_aggregation

    result = await run_daily_aggregation()
    logger.info("daily-aggregation finished: %s", result.get("status"))
    if result.get("status") == "skipped":
        sys.exit(0)
    tenants = result.get("tenants", 0)
    logger.info("processed %d tenant(s)", tenants)
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
