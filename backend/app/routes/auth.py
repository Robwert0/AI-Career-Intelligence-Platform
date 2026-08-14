from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.core.config import settings
from app.deps import get_auth_service
from app.schemas import LoginRequest, TokenResponse, UserCreate, UserRead
from app.services import AuthService
from app.services.auth_service import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)

router = APIRouter()

_REFRESH_COOKIE = "refresh_token"
_COOKIE_PATH = "/auth"


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        _REFRESH_COOKIE,
        raw_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        _REFRESH_COOKIE, path=_COOKIE_PATH, httponly=True, secure=True, samesite="strict"
    )


def _cleared_cookie_header() -> str:
    response = Response()
    _clear_refresh_cookie(response)
    return response.headers["set-cookie"]


def _unauthenticated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"set-cookie": _cleared_cookie_header()},
    )


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
    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(access_token=access_token)


@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
)
async def refresh(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    response: Response,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    if refresh_token is None:
        raise _unauthenticated()

    try:
        access_token, new_refresh_token = await auth_service.refresh(refresh_token)
    except InvalidRefreshTokenError:
        raise _unauthenticated() from None

    _set_refresh_cookie(response, new_refresh_token)

    return TokenResponse(access_token=access_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    response: Response,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> None:
    await auth_service.logout(refresh_token)
    _clear_refresh_cookie(response)
