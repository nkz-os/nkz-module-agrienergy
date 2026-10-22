"""Internal service authentication for /internal/* routes."""

from fastapi import HTTPException, Request, status

from app.config import get_settings


async def verify_internal_secret(request: Request) -> None:
    secret = request.headers.get("X-Internal-Service-Secret") or ""
    expected = get_settings().internal_service_secret
    if not expected or secret != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal service secret",
        )
