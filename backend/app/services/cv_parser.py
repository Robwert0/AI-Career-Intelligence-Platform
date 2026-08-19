import io
from collections import Counter, defaultdict

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException

from app.core.sections import HEADING_ALIASES


class UnreadablePdfError(Exception):
    """Bytes could not be opened as a PDF at all — corrupt, truncated, or not a PDF."""


def pdf_to_markdown(pdf_bytes: bytes) -> str:
    try:
        opened = pdfplumber.open(io.BytesIO(pdf_bytes))
    except PdfminerException as exc:
        raise UnreadablePdfError(str(exc)) from exc

    with opened as pdf:
        pdf_chars = [
            c
            for page in pdf.pages
            for c in page.chars
            if "(cid:" not in c["text"] and c["fontname"] not in ("Symbol", "ZapfDingbats")
        ]
        if not pdf_chars:
            return ""

        lines = defaultdict(list)
        lines_out = []
        for char in pdf_chars:
            key = round(char["doctop"])
            lines[key].append(char)

        for _, values in sorted(lines.items()):
            chars = sorted(values, key=lambda x: x["x0"])
            pieces = []
            prev = None

            for c in chars:
                if prev is not None and c["x0"] - prev["x1"] > c["size"] * 0.2:
                    pieces.append(" ")

                pieces.append(c["text"])
                prev = c

            lines_out.append(
                {
                    "text": "".join(pieces),
                    "size": chars[0]["size"],
                    "bold": bool(all("Bold" in c["fontname"] for c in chars)),
                }
            )

        final = []
        char_sizes = [round(c["size"], 1) for c in pdf_chars]
        common_size = Counter(char_sizes).most_common(1)[0][0]
        for line in lines_out:
            normalised_text = " ".join(line["text"].split()).lower()
            if (
                normalised_text in HEADING_ALIASES
                or line["bold"]
                and line["size"] > common_size * 1.1
            ):
                final.append("\n## " + line["text"])
            else:
                final.append(line["text"])

        return "\n".join(final)
