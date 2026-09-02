"""Orion-LD subscription webhook — closed-loop sensor -> algorithm -> actuator."""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.engines.shadow_engine import ShadowEngine
from app.metrics import dequeue_notify_batch, enqueue_notify_batch, observe_tracker_eval
from app.middleware import get_notification_tenant
from app.models.ngsi import NGSILDSubscriptionPayload
from app.services.intelligence_client import IntelligenceClient
from app.services.orion import get_orion
from app.services.subscriptions import PV_TYPE
from app.services.tracker_evaluator import evaluate_and_actuate_tracker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AgriEnergy Orchestrator"])

NOTIFY_MAX_CONCURRENT_TRACKERS = 20


async def _evaluate_tracker_safe(
    orion,
    intelligence_client,
    shadow_engine,
    tenant_id: str,
    tracker: dict,
    ghi: float,
    dni: float,
    dhi: float,
) -> bool:
    try:
        with observe_tracker_eval():
            await evaluate_and_actuate_tracker(
                orion, intelligence_client, shadow_engine,
                tenant_id, tracker, ghi, dni, dhi,
            )
        return True
    except Exception:
        logger.exception(
            "notify: tracker %s failed (tenant=%s)", tracker.get("id"), tenant_id)
        return False


async def process_ngsild_notification(
    tenant_id: str,
    payload: NGSILDSubscriptionPayload,
) -> None:
    """Background worker: resolve trackers and actuate in parallel."""
    orion = get_orion(tenant_id)
    intelligence_client = IntelligenceClient()
    shadow_engine = ShadowEngine()
    sem = asyncio.Semaphore(NOTIFY_MAX_CONCURRENT_TRACKERS)
    tasks: list[asyncio.Task] = []

    async def _run_one(tracker: dict, ghi: float, dni: float, dhi: float) -> bool:
        async with sem:
            return await _evaluate_tracker_safe(
                orion, intelligence_client, shadow_engine,
                tenant_id, tracker, ghi, dni, dhi,
            )

    enqueue_notify_batch()
    try:
        for entity in payload.data:
            entity_type = entity.get("type", "")
            ghi, dni, dhi = 800.0, 600.0, 200.0
            if entity_type == "WeatherObserved":
                if "illuminance" in entity:
                    ghi = float(entity["illuminance"].get("value", ghi))
                elif "solarRadiation" in entity:
                    ghi = float(entity["solarRadiation"].get("value", ghi))
                trackers = list(await orion.query_entities(type="AgriEnergyTracker", limit=500))
                trackers += await orion.query_entities(
                    type=PV_TYPE, limit=500)
            elif entity_type in (
                "AgriEnergyTracker",
                PV_TYPE,
            ):
                trackers = [entity]
            else:
                continue

            for tracker in trackers:
                tasks.append(asyncio.create_task(_run_one(tracker, ghi, dni, dhi)))

        if tasks:
            results = await asyncio.gather(*tasks)
            processed = sum(1 for ok in results if ok)
            errors = len(results) - processed
            logger.info(
                "notify batch done (tenant=%s): trackers=%d errors=%d",
                tenant_id, processed, errors,
            )
    finally:
        await orion.close()
        dequeue_notify_batch()


@router.post("/notify", status_code=status.HTTP_204_NO_CONTENT)
async def process_ngsild_notification_endpoint(
    payload: NGSILDSubscriptionPayload,
    background_tasks: BackgroundTasks,
    tenant_id: str = Depends(get_notification_tenant),
):
    """Orion-LD webhook: ack-fast, background parallel tracker evaluation.

    Answers 204 with no body: Orion-LD looks for a capitalised ``Content-Length:``
    with a case-sensitive ``strstr`` and only waives it on 204, while uvicorn always
    emits the header lower-cased. A 200 + body is therefore counted as a failed
    notification, and three consecutive failures deactivate the subscription.
    """
    logger.info(
        "NGSI-LD notification %s (tenant=%s, entities=%d)",
        payload.subscriptionId,
        tenant_id,
        len(payload.data),
    )
    background_tasks.add_task(process_ngsild_notification, tenant_id, payload)
