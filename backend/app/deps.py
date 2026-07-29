from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.repositories import UserRepository
from app.services import AuthService


def get_user_repo(session: Annotated[AsyncSession, Depends(get_db)]) -> UserRepository:
    return UserRepository(session)


def get_auth_service(repo: Annotated[UserRepository, Depends(get_user_repo)]) -> AuthService:
    return AuthService(repo)
