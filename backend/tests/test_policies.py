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


def test_chat_policies_match_the_documented_budget() -> None:
    assert policies.CHAT_USER.capacity == 20
    assert policies.CHAT_USER.refill_per_second == pytest.approx(20 / 60)
    assert policies.CHAT_USER.scope is Scope.USER
    assert policies.CHAT_IP.scope is Scope.IP


def test_chat_is_limited_more_tightly_per_user_than_per_ip() -> None:
    assert policies.CHAT_USER.capacity < policies.CHAT_IP.capacity


def test_job_intake_is_limited_to_twenty_an_hour_per_user() -> None:
    assert policies.MATCH_JOB_USER.capacity == 20
    assert policies.MATCH_JOB_USER.refill_per_second == pytest.approx(20 / 3600)
    assert policies.MATCH_JOB_USER.scope is Scope.USER


def test_job_polling_matches_the_users_me_budget() -> None:
    assert policies.MATCH_POLL_IP.capacity == 120
    assert policies.MATCH_POLL_IP.refill_per_second == pytest.approx(2.0)
    assert policies.MATCH_POLL_IP.scope is Scope.IP
    assert policies.MATCH_POLL_USER.capacity == 60
    assert policies.MATCH_POLL_USER.refill_per_second == pytest.approx(1.0)
    assert policies.MATCH_POLL_USER.scope is Scope.USER


def test_analyses_are_limited_to_five_an_hour_per_user() -> None:
    assert policies.MATCH_ANALYSIS_USER.capacity == 5
    assert policies.MATCH_ANALYSIS_USER.refill_per_second == pytest.approx(5 / 3600)
    assert policies.MATCH_ANALYSIS_USER.scope is Scope.USER
