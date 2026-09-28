import re

# A sentence, a bullet-separated clause, or a line: the shared unit both scrub.py's per-piece
# sensitivity check and evidence_extract.py's per-segment bigram grounding split text into. A
# bigram must never bridge two of these, and a sensitive clause is dropped one of these at a time.
SEGMENT_BOUNDARY = re.compile(r"(?<=[.!?;])\s+|\s+[·|•]\s+|\n+")


def cap_text(text: str, *, max_chars: int, max_bytes: int) -> tuple[str, bool]:
    """Bounds by characters first, then bytes: a non-ASCII character can take several bytes, so
    a character cap alone doesn't bound the payload size. Never splits one mid-cut."""
    encoded = text[:max_chars].encode()
    capped = encoded[:max_bytes].decode(errors="ignore")
    return capped, len(capped) < len(text)
