from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.deps import get_current_user
from app.models import User
from app.schemas import UserRead

router = APIRouter()


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserRead:
    return UserRead.model_validate(current_user)
