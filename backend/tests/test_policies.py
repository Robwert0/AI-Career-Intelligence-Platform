import inspect

import pytest

from app.core import policies
from app.core.rate_limiter import Policy, Scope
from app.deps import rate_limit


def _declared_policies() -> list[Policy]:
    return [p for p in vars(policies).values() if isinstance(p, Policy)]


def test_a_bucket_that_can_never_hold_a_token_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        Policy("bad", capacity=0, refill_per_second=1.0, scope=Scope.IP)


def test_a_bucket_holding_a_single_token_is_accepted() -> None:
    assert Policy("ok", capacity=1, refill_per_second=1.0, scope=Scope.IP).capacity == 1


def test_a_bucket_that_never_refills_is_rejected() -> None:
    with pytest.raises(ValueError, match="divides by zero"):
        Policy("bad", capacity=5, refill_per_second=0.0, scope=Scope.IP)


def test_every_declared_policy_is_valid() -> None:
    declared = _declared_policies()
    assert declared
    for policy in declared:
        assert policy.capacity >= 1
        assert policy.refill_per_second > 0


def test_register_is_the_strictest_sustained_limit() -> None:
    assert policies.REGISTER.refill_per_second == min(
        p.refill_per_second for p in _declared_policies()
    )


def test_login_keeps_its_declared_budget() -> None:
    assert policies.LOGIN.capacity == 5
    assert policies.LOGIN.refill_per_second == 1 / 60


def test_an_ip_policy_does_not_depend_on_authentication() -> None:
    parameters = inspect.signature(rate_limit(policies.LOGIN)).parameters
    assert "user" not in parameters


def test_a_user_policy_depends_on_the_current_user() -> None:
    parameters = inspect.signature(rate_limit(policies.ME_USER)).parameters
    assert "user" in parameters
