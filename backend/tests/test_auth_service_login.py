import uuid
from typing import cast

import pytest

from app.core.security import login_account_key, unregistered_login_key
from app.models import User
from app.repositories import RefreshTokenRepository, UserRepository
from app.services.auth_service import AuthService, InvalidCredentialsError, LoginAccount


class _LookupRepo:
    def __init__(self, user: User | None, canonical: str) -> None:
        self._found = (user, canonical)
        self.looked_up: list[str] = []

    async def find_login_account(self, email: str) -> tuple[User | None, str]:
        self.looked_up.append(email)
        return self._found


def _service(repo: _LookupRepo) -> AuthService:
    return AuthService(cast(UserRepository, repo), cast(RefreshTokenRepository, None))


async def test_a_registered_email_resolves_to_its_rows_key() -> None:
    user = User(id=uuid.uuid4(), email="mira@test.dev", hashed_password="x")
    repo = _LookupRepo(user, "mira@test.dev")

    account = await _service(repo).resolve_login("mİra@test.dev")

    assert account == LoginAccount(login_account_key(user.id), user)
    assert repo.looked_up == ["mİra@test.dev"]


async def test_an_unknown_email_resolves_to_the_databases_canonical_spelling() -> None:
    repo = _LookupRepo(None, "mira@test.dev")

    account = await _service(repo).resolve_login("mİra@test.dev")

    assert account == LoginAccount(unregistered_login_key("mira@test.dev"), None)


async def test_an_unknown_account_still_pays_the_bcrypt_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compared: list[str] = []

    def spy(plain_password: str, hashed_password: str) -> bool:
        compared.append(hashed_password)
        return False

    monkeypatch.setattr("app.services.auth_service.verify_password", spy)

    with pytest.raises(InvalidCredentialsError):
        await _service(_LookupRepo(None, "")).login(LoginAccount("k", None), "password1")

    assert compared and compared[0].startswith("$2b$")
