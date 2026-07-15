from fastapi import FastAPI

from app.routes.auth import router as auth_router
from app.routes.health import router as health_router

app = FastAPI(title="AI Career Intelligence Platform")
app.include_router(health_router, prefix="/health")
app.include_router(auth_router, prefix="/auth")
