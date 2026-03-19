"""
Send commands to physical tracker devices via entity-manager MQTT API.
Algorithm output (targetTilt, targetAzimuth) is published to tenant/device_id/cmd.
"""

import logging
from typing import Any, Dict

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class DeviceCommandClient:
    """
    Calls entity-manager POST /api/devices/<device_id>/commands to publish
    MQTT command. Requires tracker to have refDevice (device_id / external_id).
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = getattr(
            self.settings,
            "entity_manager_url",
            "http://entity-manager-service:5000",
        ).rstrip("/")

    async def send_tracker_command(
        self,
        tenant_id: str,
        device_id: str,
        target_tilt: float,
        target_azimuth: float = 180.0,
    ) -> bool:
        """
        Publish agrienergy.tracker.set command to device via MQTT.
        entity-manager expects X-Tenant-ID or NGSILD-Tenant for tenant context.
        """
        url = f"{self.base_url}/api/devices/{device_id}/commands"
        headers = {
            "Content-Type": "application/json",
            "NGSILD-Tenant": tenant_id,
            "X-Tenant-ID": tenant_id,
        }
        payload: Dict[str, Any] = {
            "command_type": "agrienergy.tracker.set",
            "payload": {
                "targetTilt": target_tilt,
                "targetAzimuth": target_azimuth,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code in (200, 201):
                    logger.info(
                        "Sent tracker command device_id=%s tilt=%.1f azimuth=%.1f",
                        device_id,
                        target_tilt,
                        target_azimuth,
                    )
                    return True
                logger.warning(
                    "Device command failed: %s %s",
                    response.status_code,
                    response.text[:200],
                )
                return False
        except Exception as e:
            logger.error("Device command error for %s: %s", device_id, e)
            return False
