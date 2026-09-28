import io
import re
import zipfile
import zlib
from dataclasses import dataclass
from typing import Any, Literal, NoReturn, Protocol
from xml.parsers import expat

import pdfplumber
from pdfminer.pdfdocument import PDFEncryptionError
from pdfplumber.utils.exceptions import PdfminerException

from app.core.text_hygiene import strip_invisible_unicode
from app.integrations.cv_parser import markdown_from_pdf
from app.integrations.errors import DocumentError, DocumentFailure

DocumentKind = Literal["pdf", "docx", "text"]

MAX_TEXT_CHARS = 40_000
MAX_PDF_PAGES = 10
MIN_CHARS_PER_PAGE = 200
MIN_DOCUMENT_CHARS = 200
_READ_CHUNK = 64 * 1024
_DOCX_BODY = "word/document.xml"
_MACRO_PARTS = frozenset({"vbaproject.bin", "vbadata.xml"})
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BLANK_RUNS = re.compile(r"\n{3,}")


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    kind: DocumentKind
    text: str
    pages: int | None
    truncated: bool


class AsyncReadable(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


async def read_capped(source: AsyncReadable, max_bytes: int) -> bytes:
    data = bytearray()
    while chunk := await source.read(_READ_CHUNK):
        data += chunk
        if len(data) > max_bytes:
            raise DocumentError(DocumentFailure.FILE_TOO_LARGE)
    return bytes(data)


def _open_zip(data: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile, ValueError:
        raise DocumentError(DocumentFailure.UNSUPPORTED_TYPE) from None


def sniff_type(data: bytes) -> Literal["pdf", "docx"]:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if not data.startswith(b"PK\x03\x04"):
        raise DocumentError(DocumentFailure.UNSUPPORTED_TYPE)
    with _open_zip(data) as archive:
        names = archive.namelist()
    if _DOCX_BODY not in names:
        raise DocumentError(DocumentFailure.UNSUPPORTED_TYPE)
    if any(name.rsplit("/", 1)[-1].lower() in _MACRO_PARTS for name in names):
        raise DocumentError(DocumentFailure.UNSAFE_DOCX)
    return "docx"


def _clean(text: str) -> tuple[str, bool]:
    text = strip_invisible_unicode(text)
    text = _CONTROL.sub("", text.replace("\r\n", "\n").replace("\xa0", " "))
    text = _BLANK_RUNS.sub("\n\n", text).strip()
    return text[:MAX_TEXT_CHARS], len(text) > MAX_TEXT_CHARS


def _visible_chars(text: str) -> int:
    return sum(1 for char in text if not char.isspace())


def parse_pdf(data: bytes) -> ParsedDocument:
    try:
        opened = pdfplumber.open(io.BytesIO(data))
    except PdfminerException as exc:
        if exc.args and isinstance(exc.args[0], PDFEncryptionError):
            raise DocumentError(DocumentFailure.ENCRYPTED_PDF) from None
        raise DocumentError(DocumentFailure.UNREADABLE_DOCUMENT) from None
    with opened as pdf:
        # An owner-password-only PDF opens without a password but is still encrypted.
        if pdf.doc.encryption is not None:
            raise DocumentError(DocumentFailure.ENCRYPTED_PDF)
        pages = len(pdf.pages)
        if pages == 0:
            raise DocumentError(DocumentFailure.UNREADABLE_DOCUMENT)
        if pages > MAX_PDF_PAGES:
            raise DocumentError(DocumentFailure.TOO_MANY_PAGES)
        text, truncated = _clean(markdown_from_pdf(pdf))
    if _visible_chars(text) < MIN_CHARS_PER_PAGE * pages:
        raise DocumentError(DocumentFailure.SCANNED_PDF_SUSPECTED)
    return ParsedDocument(kind="pdf", text=text, pages=pages, truncated=truncated)


def parse_pasted(text: str) -> ParsedDocument:
    cleaned, truncated = _clean(text)
    if _visible_chars(cleaned) < MIN_DOCUMENT_CHARS:
        raise DocumentError(DocumentFailure.UNREADABLE_DOCUMENT)
    return ParsedDocument(kind="text", text=cleaned, pages=None, truncated=truncated)


_W_NAMESPACES = frozenset(
    {
        "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "http://purl.oclc.org/ooxml/wordprocessingml/main",
    }
)


@dataclass(frozen=True, slots=True)
class DocxLimits:
    max_entries: int = 200
    max_total_bytes: int = 20 * 1024 * 1024
    max_ratio: int = 100


def _checked_body(archive: zipfile.ZipFile, limits: DocxLimits) -> zipfile.ZipInfo:
    entries = archive.infolist()
    if len(entries) > limits.max_entries:
        raise DocumentError(DocumentFailure.UNSAFE_DOCX)
    total = 0
    for entry in entries:
        if entry.flag_bits & 0x1 or entry.compress_type not in (
            zipfile.ZIP_STORED,
            zipfile.ZIP_DEFLATED,
        ):
            raise DocumentError(DocumentFailure.UNSAFE_DOCX)
        if entry.file_size > limits.max_ratio * max(entry.compress_size, 1):
            raise DocumentError(DocumentFailure.UNSAFE_DOCX)
        total += entry.file_size
    if total > limits.max_total_bytes:
        raise DocumentError(DocumentFailure.UNSAFE_DOCX)
    return archive.getinfo(_DOCX_BODY)


class _BodyText:
    """Collects paragraph text in document order; a table row becomes one "a | b" line."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.size = 0
        self._paragraphs: list[list[str]] = []
        self._rows: list[list[str]] = []
        self._cells: list[list[str]] = []
        self._in_text = False

    @staticmethod
    def _local(name: str) -> str | None:
        namespace, _, local = name.rpartition(" ")
        return local if namespace in _W_NAMESPACES else None

    def start(self, name: str, attributes: dict[str, str]) -> None:
        local = self._local(name)
        if local == "p":
            self._paragraphs.append([])
        elif local == "t":
            self._in_text = True
        elif local in ("tab", "br", "cr") and self._paragraphs:
            self._paragraphs[-1].append(" " if local == "tab" else "\n")
        elif local == "pStyle" and self._paragraphs:
            style = next((v for k, v in attributes.items() if k.endswith(" val")), "").lower()
            if style.startswith("heading") or style == "title":
                self._paragraphs[-1].insert(0, "## ")
        elif local == "tr":
            self._rows.append([])
        elif local == "tc":
            self._cells.append([])

    def end(self, name: str) -> None:
        local = self._local(name)
        if local == "t":
            self._in_text = False
        elif local == "p" and self._paragraphs:
            self._add("".join(self._paragraphs.pop()).strip())
        elif local == "tc" and self._cells:
            cell = " ".join(self._cells.pop())
            if self._rows:
                self._rows[-1].append(cell)
        elif local == "tr" and self._rows:
            self._add(" | ".join(cell for cell in self._rows.pop() if cell))

    def text(self, data: str) -> None:
        # Only w:t is document text: w:delText (tracked deletions) and w:instrText never count.
        if self._in_text and self._paragraphs:
            self._paragraphs[-1].append(data)

    def _add(self, line: str) -> None:
        if not line:
            return
        if self._cells:
            self._cells[-1].append(line)
            return
        self.lines.append(line)
        self.size += len(line) + 1


def _refuse_dtd(*_: Any) -> NoReturn:
    raise DocumentError(DocumentFailure.UNSAFE_DOCX)


def _body_parser(body: _BodyText) -> expat.XMLParserType:
    parser = expat.ParserCreate(namespace_separator=" ")
    # A document.xml never needs a DTD; refusing one blocks XXE and entity-expansion bombs.
    parser.StartDoctypeDeclHandler = _refuse_dtd
    parser.EntityDeclHandler = _refuse_dtd
    parser.ExternalEntityRefHandler = _refuse_dtd
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.StartElementHandler = body.start
    parser.EndElementHandler = body.end
    parser.CharacterDataHandler = body.text
    return parser


def parse_docx(data: bytes, *, limits: DocxLimits | None = None) -> ParsedDocument:
    limits = limits or DocxLimits()
    if sniff_type(data) != "docx":
        raise DocumentError(DocumentFailure.UNSUPPORTED_TYPE)
    body = _BodyText()
    parser = _body_parser(body)
    with _open_zip(data) as archive:
        info = _checked_body(archive, limits)
        inflated = 0
        try:
            with archive.open(info) as stream:
                while chunk := stream.read(_READ_CHUNK):
                    inflated += len(chunk)
                    if inflated > limits.max_total_bytes:
                        raise DocumentError(DocumentFailure.UNSAFE_DOCX)
                    parser.Parse(chunk, False)
                    if body.size > MAX_TEXT_CHARS:
                        break
                else:
                    parser.Parse(b"", True)
        except expat.ExpatError, zipfile.BadZipFile, zlib.error, EOFError:
            raise DocumentError(DocumentFailure.UNREADABLE_DOCUMENT) from None
    text, truncated = _clean("\n".join(body.lines))
    if _visible_chars(text) < MIN_DOCUMENT_CHARS:
        raise DocumentError(DocumentFailure.UNREADABLE_DOCUMENT)
    return ParsedDocument(
        kind="docx", text=text, pages=None, truncated=truncated or body.size > MAX_TEXT_CHARS
    )


def parse_document(data: bytes) -> ParsedDocument:
    return parse_pdf(data) if sniff_type(data) == "pdf" else parse_docx(data)
