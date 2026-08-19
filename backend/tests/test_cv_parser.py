from pathlib import Path

import pytest

from app.core.sections import HEADING_ALIASES, SECTIONS
from app.services.cv_parser import pdf_to_markdown

FIXTURES = Path(__file__).parent / "fixtures"
REAL_CV = Path(__file__).parents[2] / "files/RobertMirea_CV2026.pdf"

# Section counts are the whole heading-detection design in one number. c_twocolumn and d_nobold
# are expected to under-detect — see fixtures/README.md for why each one is here.
EXPECTED_SECTIONS = {
    "a_titlecase": 4,
    "b_narrowmargin": 4,
    "c_twocolumn": 2,
    "d_nobold": 2,
    "e_fusedlabels": 2,
}


def parse(name: str) -> str:
    return pdf_to_markdown((FIXTURES / f"{name}.pdf").read_bytes())


def headings(markdown: str) -> list[str]:
    return [section.split("\n")[0] for section in markdown.split("\n## ")[1:]]


def blank_pdf() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_at,
    )
    return bytes(out)


def test_a_pdf_with_no_extractable_text_yields_empty_markdown() -> None:
    assert pdf_to_markdown(blank_pdf()) == ""


@pytest.mark.parametrize(("name", "count"), sorted(EXPECTED_SECTIONS.items()))
def test_each_fixture_yields_its_expected_section_count(name: str, count: int) -> None:
    assert len(headings(parse(name))) == count


def test_title_case_headings_are_detected() -> None:
    # Proves detection is not an ALL-CAPS check: this fixture uses "Work Experience".
    assert headings(parse("a_titlecase")) == [
        "Jane Smith",
        "Work Experience",
        "Technical Skills",
        "Education",
    ]


def test_headings_are_found_when_font_metrics_cannot_discriminate() -> None:
    # 10pt headings over 9.5pt body is a ratio of 1.053, below the size margin the parser uses.
    # These are found only by matching the heading text, which is why the alias table exists.
    assert headings(parse("b_narrowmargin")) == ["Sam Patel", "EXPERIENCE", "SKILLS", "EDUCATION"]


def test_headings_are_found_without_bold() -> None:
    assert headings(parse("d_nobold")) == ["PROFESSIONAL BACKGROUND", "CORE COMPETENCIES"]


def test_a_label_column_is_separated_from_its_values() -> None:
    # The PDF draws "Languages" and "Java" as adjacent runs with no space character between
    # them. Joining characters naively fuses them into "LanguagesJava", which tokenises as one
    # word — so a search for "Java" would not match the only place it appears.
    markdown = parse("e_fusedlabels")

    assert "Languages Java, Python, SQL" in markdown
    assert "Ops & Testing Docker, CI/CD" in markdown
    assert "LanguagesJava" not in markdown


@pytest.mark.parametrize("name", sorted(EXPECTED_SECTIONS))
def test_no_cid_artifacts_survive(name: str) -> None:
    assert "(cid:" not in parse(name)


def test_the_artifact_filter_does_not_eat_real_words() -> None:
    # "incident" contains "cid". Filtering on that substring rather than the "(cid:" pattern
    # silently deletes the word, and the only evidence is its absence.
    assert "incident response" in parse("e_fusedlabels")


def test_output_splits_into_sections_on_the_chunker_delimiter() -> None:
    # The chunker splits on "\n## ", so a heading emitted as "###" or without the trailing
    # space would leave the whole document as a single section.
    markdown = parse("e_fusedlabels")

    assert markdown.split("\n## ")[1].startswith("EXPERIENCE")
    assert len(markdown.split("\n## ")) == 3


def test_every_alias_maps_to_a_storable_section() -> None:
    # chunks.section carries a CHECK constraint over SECTIONS, so an alias pointing anywhere
    # else fails at insert time rather than here.
    assert set(HEADING_ALIASES.values()) <= set(SECTIONS)


@pytest.mark.skipif(not REAL_CV.exists(), reason="personal CV not present")
def test_the_real_cv_parses_into_its_seven_sections() -> None:
    # Couples to Robert's actual CV: update this if the document's headings change.
    markdown = pdf_to_markdown(REAL_CV.read_bytes())

    assert headings(markdown) == [
        "Robert Mirea",
        "SUMMARY",
        "EXPERIENCE",
        "PROJECTS",
        "SKILLS",
        "EDUCATION",
        "LANGUAGES",
    ]
    assert "Languages Java, Python, SQL, TypeScript, C++" in markdown
    assert "(cid:" not in markdown
