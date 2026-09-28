import io
import zipfile

W_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
)
CV_LINE = "Backend engineer at Acme building Go services and PostgreSQL schemas for payments."


def _pdf_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[str], *, encrypted: bool = False) -> bytes:
    """A minimal PDF drawing each page's lines in Helvetica, which pdfplumber reads back."""
    page_ids = [4 + 2 * index for index in range(len(pages))]
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for page_id, text in zip(page_ids, pages, strict=True):
        ops = ["BT", "/F1 10 Tf", "12 TL", "40 800 Td"]
        ops += [f"({_pdf_string(line)}) Tj T*" for line in text.splitlines()]
        stream = "\n".join([*ops, "ET"]).encode("latin-1")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    trailer = f"<< /Size {len(objects) + 1} /Root 1 0 R"
    if encrypted:
        # A Standard security handler whose keys match no password, so pdfminer cannot open it.
        trailer += (
            " /Encrypt << /Filter /Standard /V 1 /R 2 /P -4 "
            f"/O <{'11' * 32}> /U <{'22' * 32}> >> /ID [<{'33' * 16}> <{'33' * 16}>]"
        )
    out += f"trailer\n{trailer} >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    return bytes(out)


def text_page(lines: int = 30) -> str:
    return "\n".join(CV_LINE for _ in range(lines))


def paragraph(text: str, *, style: str | None = None) -> str:
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{props}<w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


def table(rows: list[list[str]]) -> str:
    body = "".join(
        "<w:tr>" + "".join(f"<w:tc>{paragraph(cell)}</w:tc>" for cell in row) + "</w:tr>"
        for row in rows
    )
    return f"<w:tbl>{body}</w:tbl>"


def document_xml(body: str, *, prolog: str = "") -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>{prolog}'
        f'<w:document xmlns:w="{W_NAMESPACE}"><w:body>{body}</w:body></w:document>'
    )


def make_docx(
    body: str = "",
    *,
    xml: str | None = None,
    extra: dict[str, bytes] | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("word/document.xml", xml if xml is not None else document_xml(body))
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


def cv_docx() -> bytes:
    return make_docx(
        paragraph("Experience", style="Heading1")
        + "".join(paragraph(CV_LINE) for _ in range(4))
        + table([["Skill", "Level"], ["Go", "Expert"]])
    )
