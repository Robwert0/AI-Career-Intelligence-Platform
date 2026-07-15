from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.config import settings
from app.deps import get_auth_service
from app.schemas import LoginRequest, TokenResponse, UserCreate, UserRead
from app.services import AuthService
from app.services.auth_service import EmailAlreadyRegisteredError, InvalidCredentialsError

router = APIRouter()


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserRead,
)
async def register(
    data: UserCreate,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserRead:
    try:
        user = await auth_service.register(data)
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from None

    return UserRead.model_validate(user)


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
)
async def login(
    data: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    response: Response,
) -> TokenResponse:
    try:
        access_token, refresh_token = await auth_service.login(
            email=data.email, password=data.password
        )
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from None
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path="/auth",
    )

    return TokenResponse(access_token=access_token)
