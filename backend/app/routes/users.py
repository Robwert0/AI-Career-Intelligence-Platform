from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core import policies
from app.deps import get_current_user, rate_limit
from app.models import User
from app.schemas import UserRead

router = APIRouter()


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(rate_limit(policies.ME_IP)),
        Depends(rate_limit(policies.ME_USER)),
    ],
)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserRead:
    return UserRead.model_validate(current_user)
