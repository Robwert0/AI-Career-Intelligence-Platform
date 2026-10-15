from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.core import policies
from app.core.config import settings
from app.core.rate_limiter import Limiter, Policy
from app.core.security import create_login_device_token, login_account_key, login_device_id
from app.deps import (
    failure_rate_limit,
    get_auth_service,
    get_global_identity,
    get_limiter,
    rate_limit,
    reserved_rate_limit,
)
from app.schemas import LoginRequest, TokenResponse, UserCreate, UserRead
from app.services import AuthService
from app.services.auth_service import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)

router = APIRouter()

# __Host- makes the browser refuse this name with a Domain attribute or a non-root Path,
# which is what stops a sibling subdomain planting a duplicate. The prefix requires Path=/.
_REFRESH_COOKIE = "__Host-refresh_token"
_DEVICE_COOKIE = "__Host-login_device"
_COOKIE_PATH = "/"


# Strict, not Lax or None: the browser only ever talks to the frontend origin, which proxies
# /api/* to this API, so every request carrying this cookie is same-site. Lax would buy nothing
# (it relaxes only cross-site top-level GETs, never a fetch POST) and None would make the cookie
# third-party, which Safari's ITP blocks outright.
_SAMESITE: Literal["strict"] = "strict"


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        _REFRESH_COOKIE,
        raw_token,
        httponly=True,
        secure=True,
        samesite=_SAMESITE,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=_COOKIE_PATH,
    )


def _set_device_cookie(response: Response, account_key: str) -> None:
    response.set_cookie(
        _DEVICE_COOKIE,
        create_login_device_token(account_key),
        httponly=True,
        secure=True,
        samesite=_SAMESITE,
        max_age=settings.login_device_expire_days * 24 * 60 * 60,
        path=_COOKIE_PATH,
    )


def _login_bucket(account_key: str, device_token: str | None) -> tuple[Policy, str]:
    # A browser that has signed in to this account before gets its own failure budget, so an
    # attacker draining the account's shared one cannot lock the owner out of a known device.
    device_id = None if device_token is None else login_device_id(device_token, account_key)
    if device_id is None:
        return policies.LOGIN_ACCOUNT, account_key
    return policies.LOGIN_DEVICE, device_id


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        _REFRESH_COOKIE, path=_COOKIE_PATH, httponly=True, secure=True, samesite=_SAMESITE
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
    # Narrowest first, so a client that is already refused does not spend the wider budgets.
    dependencies=[
        Depends(rate_limit(policies.REGISTER)),
        Depends(rate_limit(policies.REGISTER_PREFIX)),
        Depends(rate_limit(policies.REGISTER_ATTEMPTS_GLOBAL)),
    ],
)
async def register(
    data: UserCreate,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    limiter: Annotated[Limiter, Depends(get_limiter)],
    global_identity: Annotated[str, Depends(get_global_identity)],
) -> UserRead:
    # Taken in the body, after validation, and refunded on any failure (409 included), so only
    # created accounts spend the ceiling and 422s never reach it.
    async with reserved_rate_limit(policies.REGISTER_GLOBAL, global_identity, limiter):
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
    dependencies=[
        Depends(rate_limit(policies.LOGIN)),
        Depends(rate_limit(policies.LOGIN_PREFIX)),
    ],
)
async def login(
    data: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    limiter: Annotated[Limiter, Depends(get_limiter)],
    response: Response,
    device_token: Annotated[str | None, Cookie(alias=_DEVICE_COOKIE)] = None,
) -> TokenResponse:
    # Charged for every submitted email, registered or not, so the limit leaks no existence.
    account_key = login_account_key(data.email)
    policy, identity = _login_bucket(account_key, device_token)
    async with failure_rate_limit(policy, identity, limiter):
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
    _set_device_cookie(response, account_key)

    return TokenResponse(access_token=access_token)


@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit(policies.REFRESH))],
)
async def refresh(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    response: Response,
    refresh_token: Annotated[str | None, Cookie(alias=_REFRESH_COOKIE)] = None,
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
    dependencies=[Depends(rate_limit(policies.LOGOUT))],
)
async def logout(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    response: Response,
    refresh_token: Annotated[str | None, Cookie(alias=_REFRESH_COOKIE)] = None,
) -> None:
    await auth_service.logout(refresh_token)
    _clear_refresh_cookie(response)
