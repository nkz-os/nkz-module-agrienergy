"""Admin routes (role-protected)."""

from fastapi import APIRouter, Depends

from app.middleware import TokenPayload, require_roles

router = APIRouter(tags=["AgriEnergy Orchestrator"])


@router.get("/admin/stats")
async def get_stats(
    user: TokenPayload = Depends(require_roles("TenantAdmin", "PlatformAdmin")),
):
    """Module statistics. Requires TenantAdmin or PlatformAdmin."""
    return {
        "total_tenants": 0,
        "total_items": 0,
        "user": user.email,
    }
