from app.services.match_failures import describe_failure


def test_an_overlong_posting_asks_for_a_shorter_paste() -> None:
    failure = describe_failure("input_too_long")

    assert (failure.code, failure.recovery) == ("input_too_long", "paste")
    assert "too long" in failure.message
