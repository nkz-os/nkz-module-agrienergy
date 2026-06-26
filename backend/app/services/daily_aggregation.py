"""Daily energy aggregation: timeseries Wh integral → FinBridge / Orion snapshot."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.services.energy_integrator import trapezoidal_wh
from app.services.finbridge_client import FinBridgeEmitter
from app.services.ngsi_helpers import ref_agri_parcel_from_entity
from app.services.orion import get_orion, prop
from app.services.timeseries_client import TimeseriesReaderClient

logger = logging.getLogger(__name__)

TRACKER_TYPES = ("AgriEnergyTracker", "https://saref.etsi.org/saref4agri/PhotovoltaicInstallation")


def _day_window(target_day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(target_day, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def _ref_device_id(tracker: dict) -> str | None:
    ref = tracker.get("refDevice", {}).get("value") or tracker.get("refDevice")
    if isinstance(ref, str) and ref.strip():
        return ref.strip()
    return None


async def aggregate_tracker_day(
    tenant_id: str,
    tracker: dict,
    target_day: date,
    ts_client: TimeseriesReaderClient,
    finbridge: FinBridgeEmitter,
    *,
    emit_finbridge: bool = True,
    write_orion: bool = True,
) -> dict[str, Any]:
    """Compute Wh for one tracker on ``target_day`` and emit to FinBridge."""
    tracker_id = tracker.get("id")
    if not tracker_id:
        return {"tracker_id": None, "skipped": True, "reason": "no_id"}

    since, until = _day_window(target_day)
    entity_candidates = [tracker_id]
    device_id = _ref_device_id(tracker)
    if device_id and device_id not in entity_candidates:
        entity_candidates.append(device_id)

    points: list[dict] = []
    source_entity = tracker_id
    for eid in entity_candidates:
        points = await ts_client.fetch_power_series(eid, since, until)
        if points:
            source_entity = eid
            break

    generation_wh = trapezoidal_wh(points)
    result: dict[str, Any] = {
        "tracker_id": tracker_id,
        "date": target_day.isoformat(),
        "generation_wh": generation_wh,
        "sample_count": len(points),
        "source_entity": source_entity,
        "skipped": generation_wh <= 0.0 and len(points) < 2,
    }

    if result["skipped"]:
        logger.info(
            "aggregation: skip tracker %s (no usable power series, tenant=%s)",
            tracker_id, tenant_id,
        )
        return result

    if emit_finbridge:
        await finbridge.emit_daily_aggregation(
            tenant_id=tenant_id,
            tracker_id=tracker_id,
            generation_wh=generation_wh,
            consumption_wh=0.0,
            aggregation_date=target_day,
        )
        result["finbridge"] = "emitted"

    if write_orion:
        orion = get_orion(tenant_id)
        try:
            await orion.append_entity_attrs(tracker_id, {
                "dailyGenerationWh": prop(generation_wh),
                "dailyGenerationDate": prop(target_day.isoformat()),
            })
            result["orion"] = "updated"
        finally:
            await orion.close()

    logger.info(
        "aggregation: tracker %s day=%s Wh=%.2f samples=%d",
        tracker_id, target_day, generation_wh, len(points),
    )
    return result


async def run_tenant_daily_aggregation(
    tenant_id: str,
    target_day: date | None = None,
    *,
    emit_finbridge: bool = True,
    write_orion: bool = True,
) -> dict[str, Any]:
    """Aggregate all trackers for a tenant on the target UTC day (default: yesterday)."""
    if target_day is None:
        target_day = (datetime.now(timezone.utc).date() - timedelta(days=1))

    orion = get_orion(tenant_id)
    ts_client = TimeseriesReaderClient(tenant_id)
    finbridge = FinBridgeEmitter()
    trackers: list[dict] = []
    try:
        for ttype in TRACKER_TYPES:
            trackers.extend(await orion.query_entities(type=ttype, limit=500))
    finally:
        await orion.close()

    results: list[dict[str, Any]] = []
    try:
        for tracker in trackers:
            if not ref_agri_parcel_from_entity(tracker) and not tracker.get("hasAgriParcel"):
                continue
            results.append(await aggregate_tracker_day(
                tenant_id, tracker, target_day, ts_client, finbridge,
                emit_finbridge=emit_finbridge,
                write_orion=write_orion,
            ))
    finally:
        await ts_client.close()

    emitted = sum(1 for r in results if r.get("finbridge") == "emitted")
    return {
        "tenant_id": tenant_id,
        "date": target_day.isoformat(),
        "trackers_processed": len(results),
        "finbridge_emitted": emitted,
        "results": results,
    }


async def run_daily_aggregation(
    tenant_ids: list[str] | None = None,
    target_day: date | None = None,
) -> dict[str, Any]:
    """Run daily aggregation for all given tenants (or discover from env/DB)."""
    from app.tenants import discover_tenants

    tenants = tenant_ids or discover_tenants()
    if not tenants:
        return {"status": "skipped", "reason": "no_tenants"}

    summaries = []
    for tenant_id in tenants:
        summaries.append(await run_tenant_daily_aggregation(tenant_id, target_day))

    return {
        "status": "ok",
        "tenants": len(summaries),
        "summaries": summaries,
    }
