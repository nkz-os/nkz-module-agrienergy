"""AgriEnergy API router composition."""

from fastapi import APIRouter

from app.api import admin, internal, notify, parks, simulate, status
from app.api.deps import get_orion
from app.engines.elevation import ElevationService
from app.services.device_command_client import DeviceCommandClient
from app.services.intelligence_client import IntelligenceClient

# Re-exported for test monkeypatching (conftest patches app.api.*).
__all__ = [
    "router",
    "get_orion",
    "IntelligenceClient",
    "DeviceCommandClient",
    "ElevationService",
]

router = APIRouter(tags=["AgriEnergy Orchestrator"])
router.include_router(status.router)
router.include_router(parks.router)
router.include_router(simulate.router)
router.include_router(notify.router)
router.include_router(admin.router)
router.include_router(internal.router)
