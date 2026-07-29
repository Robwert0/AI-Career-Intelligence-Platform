from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.users import router as users_router

app = FastAPI(title="AI Career Intelligence Platform")
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
