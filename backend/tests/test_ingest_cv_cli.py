import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from ingest_cv import document_id_for  # noqa: E402


def test_the_same_bytes_always_produce_the_same_document_id() -> None:
    pdf = (FIXTURES / "a_titlecase.pdf").read_bytes()
    assert document_id_for(pdf) == document_id_for(pdf)


def test_the_id_is_pinned_so_a_namespace_change_cannot_pass_unnoticed() -> None:
    pdf = (FIXTURES / "a_titlecase.pdf").read_bytes()
    assert str(document_id_for(pdf)) == "1b742676-e5dc-570d-a61e-bb7c8731bc06"


def test_different_documents_get_different_ids() -> None:
    a = (FIXTURES / "a_titlecase.pdf").read_bytes()
    b = (FIXTURES / "b_narrowmargin.pdf").read_bytes()
    assert document_id_for(a) != document_id_for(b)


def test_editing_a_document_produces_a_new_id() -> None:
    pdf = (FIXTURES / "a_titlecase.pdf").read_bytes()
    assert document_id_for(pdf) != document_id_for(pdf + b" ")
