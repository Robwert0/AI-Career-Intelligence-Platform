from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.deps import verify_trusted_origin
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.users import router as users_router

app = FastAPI(
    title="AI Career Intelligence Platform", dependencies=[Depends(verify_trusted_origin)]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(health_router, prefix="/health")
app.include_router(auth_router, prefix="/auth")
app.include_router(users_router, prefix="/users")

_REFLECTED_KEYS = frozenset({"input", "ctx"})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = [
        {key: value for key, value in error.items() if key not in _REFLECTED_KEYS}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": detail}
    )
