"""Admin routes (role-protected)."""

from fastapi import APIRouter

from nkz_platform_sdk.auth import AuthContext

from app.middleware import require_roles

router = APIRouter(tags=["AgriEnergy Orchestrator"])


@router.get("/admin/stats")
async def get_stats(
    user: AuthContext = require_roles("TenantAdmin", "PlatformAdmin"),
):
    """Module statistics. Requires TenantAdmin or PlatformAdmin."""
    return {
        "total_tenants": 0,
        "total_items": 0,
        "user": user.user_id,
    }
