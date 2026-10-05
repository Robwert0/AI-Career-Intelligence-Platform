from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core import policies
from app.deps import get_admin_service, get_current_admin, rate_limit
from app.schemas.admin import AdminUsersPage
from app.services.admin_service import AdminService

router = APIRouter()


@router.get(
    "/users",
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(rate_limit(policies.ADMIN_IP)),
        Depends(get_current_admin),
        Depends(rate_limit(policies.ADMIN_USER)),
    ],
)
async def list_users(
    service: Annotated[AdminService, Depends(get_admin_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminUsersPage:
    return await service.list_users(limit, offset)
