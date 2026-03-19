import httpx
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Strict timeout for evaluate_status: /notify is event-driven; blocking would exhaust
# the pool with many trackers. Intelligence must respond via fast read (precomputed cache/
# Redis or Context Broker). Max 200 ms; ideally Intelligence < 50 ms.
EVALUATE_STATUS_TIMEOUT_S = 0.2


class IntelligenceClient:
    """
    Client for NKZ-Intelligence: hydric stress (legacy) and evaluate_status (scalar bundle for algorithm context).
    """

    def __init__(self):
        self.base_url = "http://api-gateway:8080/api/intelligence"

    async def evaluate_hydric_stress(
        self,
        tenant_id: str,
        parcel_id: str,
        shadow_polygon: List[tuple],
        current_soil_moisture: float,
    ) -> float:
        """Legacy: returns stress_index only. Prefer evaluate_status for full scalar bundle."""
        headers = {"NGSILD-Tenant": tenant_id, "X-Tenant-ID": tenant_id}
        payload = {
            "parcel_id": parcel_id,
            "soil_moisture": current_soil_moisture,
            "shadow_projection": shadow_polygon,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    f"{self.base_url}/evaluate-stress",
                    json=payload,
                    headers=headers,
                )
                if res.status_code == 200:
                    return res.json().get("stress_index", 0.0)
                return 0.0
        except Exception as e:
            logger.error("Biological Handshake failed for %s: %s", parcel_id, e)
            return 0.0

    async def evaluate_status(
        self,
        tenant_id: str,
        tracker_id: str,
        parcel_id: str,
        timestamp: str,
        shadow_polygon_2d: List[Any],
        telemetry: Dict[str, Any],
    ) -> Dict[str, float]:
        """
        POST /api/intelligence/evaluate_status. Returns scalar bundle for context["biology"].
        On timeout or 5xx returns {} so caller can inject safe defaults (fail-safe).
        """
        headers = {"NGSILD-Tenant": tenant_id, "X-Tenant-ID": tenant_id, "Content-Type": "application/json"}
        payload = {
            "tracker_id": tracker_id,
            "parcel_id": parcel_id,
            "timestamp": timestamp,
            "shadow_polygon_2d": shadow_polygon_2d,
            "telemetry": telemetry,
        }
        try:
            async with httpx.AsyncClient(timeout=EVALUATE_STATUS_TIMEOUT_S) as client:
                res = await client.post(
                    f"{self.base_url}/evaluate_status",
                    json=payload,
                    headers=headers,
                )
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, dict):
                        return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}
                    return {}
                return {}
        except Exception as e:
            logger.warning("evaluate_status failed for %s: %s", tracker_id, e)
            return {}
