from app.ai.match.text_limits import SEGMENT_BOUNDARY, cap_text


def test_cap_text_bounds_by_characters_then_bytes() -> None:
    emoji = "\U0001f600"

    capped, truncated = cap_text(emoji * 100, max_chars=50, max_bytes=40)

    assert truncated is True
    assert capped.count(emoji) == 10


def test_cap_text_never_splits_a_multibyte_character() -> None:
    capped, _ = cap_text("a" + "é" * 100, max_chars=50, max_bytes=90)

    assert "�" not in capped


def test_cap_text_reports_no_cut_when_the_text_already_fits() -> None:
    capped, truncated = cap_text("hello", max_chars=50, max_bytes=90)

    assert (capped, truncated) == ("hello", False)


def test_segment_boundary_splits_on_sentences_bullets_and_lines() -> None:
    pieces = SEGMENT_BOUNDARY.split("First sentence. Second sentence · Bulleted\nThird line")

    assert pieces == ["First sentence.", "Second sentence", "Bulleted", "Third line"]
