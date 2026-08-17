from pathlib import Path

import pytest

from app.ai.chunking import _SEPARATORS, TextChunk, _pack, chunk_cv
from app.ai.tokenizer import count_tokens, token_budget
from app.core.sections import SECTIONS
from app.services.cv_parser import pdf_to_markdown

FIXTURES = Path(__file__).parent / "fixtures"
REAL_CV = Path(__file__).parents[2] / "files/RobertMirea_CV2026.pdf"

MARKDOWN_FIXTURES = ["sample_cv.md", "f_oversized.md"]


def chunk_fixture(name: str) -> list[TextChunk]:
    return chunk_cv((FIXTURES / name).read_text())


def oversized_text(tokens: int = 700) -> str:
    # No periods, so the sentence separator cannot split it — forces the word level too.
    return " ".join(["word"] * tokens)


@pytest.mark.parametrize("name", MARKDOWN_FIXTURES)
def test_every_chunk_fits_the_token_budget(name: str) -> None:
    # The invariant the whole FIT step exists for. An over-budget chunk is silently truncated by
    # the embedder, so the tail of it is never indexed and nothing reports a problem.
    for chunk in chunk_fixture(name):
        assert count_tokens(chunk.content) <= token_budget(), chunk.content[:60]


@pytest.mark.parametrize("name", MARKDOWN_FIXTURES)
def test_chunk_index_is_sequential_across_the_document(name: str) -> None:
    # chunks.chunk_index carries UniqueConstraint(document_id, chunk_index): a per-section
    # counter would repeat 0 and the second insert would raise IntegrityError.
    chunks = chunk_fixture(name)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize("name", MARKDOWN_FIXTURES)
def test_every_section_is_one_the_database_accepts(name: str) -> None:
    # chunks.section has a CHECK constraint over SECTIONS; anything else fails at insert time.
    for chunk in chunk_fixture(name):
        assert chunk.section in SECTIONS


@pytest.mark.parametrize("name", MARKDOWN_FIXTURES)
def test_no_chunk_is_blank(name: str) -> None:
    for chunk in chunk_fixture(name):
        assert chunk.content.strip()


def test_a_split_section_repeats_its_heading_on_every_chunk() -> None:
    # Both legs of hybrid retrieval depend on this: a chunk whose text omits "Work Experience"
    # has no section signal in its vector, and search_vector is generated from content.
    experience = [c for c in chunk_fixture("f_oversized.md") if c.section == "experience"]

    assert len(experience) > 1
    assert all(c.content.startswith("Work Experience") for c in experience)


def test_an_oversized_paragraph_is_split_at_sentence_boundaries() -> None:
    # projects is one 604-token paragraph, so paragraph packing cannot help it.
    projects = [c for c in chunk_fixture("f_oversized.md") if c.section == "projects"]

    assert len(projects) > 1
    assert all(count_tokens(c.content) <= token_budget() for c in projects)


def test_sub_headings_stay_inside_their_section() -> None:
    # The delimiter is "\n## " including the trailing space. Without it "\n###" matches too and
    # every "### job title" becomes its own section, labelled "other".
    chunks = chunk_fixture("sample_cv.md")
    experience = [c for c in chunks if c.section == "experience"]

    assert len(experience) == 1
    assert "### Senior Backend Engineer" in experience[0].content
    assert not any(c.content.startswith("### ") for c in chunks)


def test_an_unrecognised_heading_becomes_other() -> None:
    chunks = chunk_cv("\n## Beekeeping\n\nTwo hives since 2019.")

    assert [c.section for c in chunks] == ["other"]


def test_content_keeps_the_heading_rather_than_only_the_body() -> None:
    chunks = chunk_cv("\n## Technical Skills\n\nPython, Rust.")

    assert chunks[0].content == "Technical Skills\n\nPython, Rust."


def test_pack_keeps_units_together_while_they_fit() -> None:
    groups = _pack(["alpha", "beta", "gamma"], _SEPARATORS, token_budget())

    assert groups == ["alpha\n\nbeta\n\ngamma"]


def test_pack_splits_a_unit_that_cannot_fit_on_its_own() -> None:
    groups = _pack([oversized_text()], _SEPARATORS, token_budget())

    assert len(groups) > 1
    assert all(count_tokens(g) <= token_budget() for g in groups)


def test_pack_preserves_document_order_around_an_oversized_unit() -> None:
    # current must be flushed BEFORE recursing. Otherwise the oversized unit's pieces land in
    # groups ahead of the group already accumulating: every chunk still fits, every count is
    # still right, and chunk_index claims an order the document does not have.
    groups = _pack(["FIRST", oversized_text(), "LAST"], _SEPARATORS, token_budget())

    assert groups[0] == "FIRST"
    assert groups[-1] == "LAST"


def test_pack_keeps_a_single_over_budget_unit_rather_than_dropping_it() -> None:
    # At the word level there is nothing finer, and splitting mid-word would corrupt both
    # halves' embeddings. Emitting it oversized beats deleting the text.
    monster = "x" * 4000

    groups = _pack([monster], _SEPARATORS, token_budget())

    assert "".join(groups).count("x") == 4000


@pytest.mark.skipif(not REAL_CV.exists(), reason="personal CV not present")
def test_the_parser_and_chunker_compose_on_a_real_pdf() -> None:
    chunks = chunk_cv(pdf_to_markdown(REAL_CV.read_bytes()))

    assert [c.section for c in chunks] == [
        "other",
        "summary",
        "experience",
        "projects",
        "skills",
        "education",
        "languages",
    ]
    assert all(count_tokens(c.content) <= token_budget() for c in chunks)
