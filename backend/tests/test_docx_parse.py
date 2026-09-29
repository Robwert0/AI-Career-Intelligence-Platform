import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from documents import (
    CV_LINE,
    cv_docx,
    document_xml,
    make_docx,
    make_pdf,
    paragraph,
    text_page,
)

from app.integrations.doc_parse import (
    MAX_TEXT_CHARS,
    DocxLimits,
    parse_document,
    parse_docx,
)
from app.integrations.errors import DocumentError, DocumentFailure

REAL_CV = Path(__file__).parents[2] / "files/RobertMirea_CV2026.pdf"


def failure_of[T](parse: Callable[[T], object], data: T) -> DocumentFailure:
    with pytest.raises(DocumentError) as caught:
        parse(data)
    return caught.value.failure


def test_a_docx_parses_paragraphs_headings_and_tables_in_order() -> None:
    parsed = parse_docx(cv_docx())

    assert parsed.kind == "docx"
    lines = parsed.text.splitlines()
    assert lines[0] == "## Experience"
    assert lines[1] == CV_LINE
    assert lines[-2:] == ["Skill | Level", "Go | Expert"]


def test_tracked_deletions_and_field_codes_are_not_read() -> None:
    body = "".join(paragraph(CV_LINE) for _ in range(3)) + (
        "<w:p><w:del><w:r><w:delText>Fired for misconduct</w:delText></w:r></w:del>"
        '<w:r><w:instrText> HYPERLINK "https://evil.example" </w:instrText></w:r>'
        "<w:r><w:t>Kept sentence.</w:t></w:r></w:p>"
    )

    text = parse_docx(make_docx(body)).text

    assert "Kept sentence." in text
    assert "misconduct" not in text
    assert "evil.example" not in text


def test_strict_ooxml_namespaces_are_read() -> None:
    strict = "http://purl.oclc.org/ooxml/wordprocessingml/main"
    xml = document_xml("".join(paragraph(CV_LINE) for _ in range(4))).replace(
        "http://schemas.openxmlformats.org/wordprocessingml/2006/main", strict
    )

    assert CV_LINE in parse_docx(make_docx(xml=xml)).text


def test_an_external_entity_is_refused_before_it_resolves() -> None:
    xxe = document_xml(
        paragraph("&xxe;" + CV_LINE * 4),
        prolog='<!DOCTYPE w:document [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>',
    )

    assert failure_of(parse_docx, make_docx(xml=xxe)) is DocumentFailure.UNSAFE_DOCX


def test_an_entity_expansion_bomb_is_refused() -> None:
    laughs = "".join(f'<!ENTITY l{n} "{f"&l{n - 1};" * 10 if n else "lol"}">' for n in range(10))
    bomb = document_xml(paragraph("&l9;"), prolog=f"<!DOCTYPE w:document [{laughs}]>")

    assert failure_of(parse_docx, make_docx(xml=bomb)) is DocumentFailure.UNSAFE_DOCX


def test_an_undeclared_entity_is_unreadable_not_resolved() -> None:
    xml = document_xml(paragraph("&secret;" + CV_LINE * 4))

    assert failure_of(parse_docx, make_docx(xml=xml)) is DocumentFailure.UNREADABLE_DOCUMENT


def test_a_highly_compressed_entry_is_a_zip_bomb() -> None:
    bomb = make_docx(paragraph(CV_LINE), extra={"word/media/filler.xml": b" " * 5_000_000})

    assert failure_of(parse_docx, bomb) is DocumentFailure.UNSAFE_DOCX


def test_too_many_entries_is_unsafe() -> None:
    crowded = make_docx(
        paragraph(CV_LINE), extra={f"word/media/{n}.bin": bytes([n]) for n in range(5)}
    )

    with pytest.raises(DocumentError) as caught:
        parse_docx(crowded, limits=DocxLimits(max_entries=4))

    assert caught.value.failure is DocumentFailure.UNSAFE_DOCX


def test_too_much_uncompressed_data_is_unsafe() -> None:
    stored = make_docx(paragraph(CV_LINE * 4), compression=zipfile.ZIP_STORED)

    with pytest.raises(DocumentError) as caught:
        parse_docx(stored, limits=DocxLimits(max_total_bytes=500))

    assert caught.value.failure is DocumentFailure.UNSAFE_DOCX


def test_an_encrypted_zip_entry_is_unsafe() -> None:
    data = bytearray(cv_docx())
    # Set the "encrypted" flag bit on the first central-directory record.
    central = data.index(b"PK\x01\x02")
    data[central + 8] |= 0x1

    assert failure_of(parse_docx, bytes(data)) is DocumentFailure.UNSAFE_DOCX


def test_malformed_xml_is_unreadable() -> None:
    broken = make_docx(xml="<w:document><w:body><w:p>")

    assert failure_of(parse_docx, broken) is DocumentFailure.UNREADABLE_DOCUMENT


def test_a_docx_with_almost_no_text_is_unreadable() -> None:
    assert failure_of(parse_docx, make_docx(paragraph("CV"))) is (
        DocumentFailure.UNREADABLE_DOCUMENT
    )


def test_docx_text_is_capped() -> None:
    # Numbered lines keep the compression ratio realistic, below the zip-bomb threshold.
    huge = make_docx("".join(paragraph(f"{n:05d} {CV_LINE[: n % 80]}") for n in range(4_000)))

    parsed = parse_docx(huge)

    assert parsed.truncated is True
    assert len(parsed.text) == MAX_TEXT_CHARS


def test_parse_document_dispatches_on_the_magic_bytes() -> None:
    assert parse_document(make_pdf([text_page()])).kind == "pdf"
    assert parse_document(cv_docx()).kind == "docx"
