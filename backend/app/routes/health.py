from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.env}
