"""FastAPI dependencies shared across API routers."""

from fastapi import Depends

from app.middleware import get_tenant_id
from app.services.orion import get_orion

__all__ = ["get_orion", "orion_dep"]


async def orion_dep(tenant_id: str = Depends(get_tenant_id)):
    """Per-request, tenant-scoped OrionClient; closed after the response."""
    orion = get_orion(tenant_id)
    try:
        yield orion
    finally:
        await orion.close()
