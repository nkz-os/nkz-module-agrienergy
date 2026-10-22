"""Internal routes (cluster-only, X-Internal-Service-Secret)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.middleware.internal_auth import verify_internal_secret
from app.services.daily_aggregation import run_daily_aggregation, run_tenant_daily_aggregation

router = APIRouter(tags=["AgriEnergy Internal"])


@router.post("/internal/daily-aggregation", status_code=200)
async def trigger_daily_aggregation(
    _: None = Depends(verify_internal_secret),
    tenant_id: str | None = Query(None, description="Single tenant; omit for all discovered tenants"),
    day: str | None = Query(None, description="UTC day YYYY-MM-DD (default: yesterday)"),
):
    """Trigger daily Wh aggregation (cron escape hatch / manual replay)."""
    target_day: date | None = None
    if day:
        try:
            target_day = date.fromisoformat(day)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid day format (YYYY-MM-DD)") from exc

    if tenant_id:
        summary = await run_tenant_daily_aggregation(tenant_id, target_day)
        return {"status": "ok", "summary": summary}

    result = await run_daily_aggregation(target_day=target_day)
    return result
