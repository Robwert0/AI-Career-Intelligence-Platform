import re

from app.ai.redaction import redact_phone_numbers

EMAIL_PLACEHOLDER = "[email redacted]"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Characteristics a match must never weigh (spec §5.4), plus identity numbers. A sentence that
# mentions one is dropped whole: masking only the value would still leave "Nationality: ___".
_SENSITIVE = re.compile(
    r"\b(?:date\s+of\s+birth|d\.?o\.?b\b|birth\s*date|born\s+(?:on|in)\b|\d{1,3}\s+years?\s+old"
    r"|age\s*:|marital|married|divorced|widowed|spouse|nationality|citizenship|citizen\s+of"
    r"|religio|gender|sex\s*:|pregnan|disabilit|disabled|passport|national\s+id|id\s+number"
    r"|identity\s+card|social\s+security|\bssn\b|\bcnp\b|photo)",
    re.IGNORECASE,
)
_PIECES = re.compile(r"(?<=[.!?;])\s+|\s+[·|•]\s+|\n+")


def mentions_sensitive(text: str) -> bool:
    return _SENSITIVE.search(text) is not None


def mask_contacts(text: str) -> str:
    return redact_phone_numbers(_EMAIL.sub(EMAIL_PLACEHOLDER, text)).strip()


def scrub_evidence_text(text: str) -> str:
    """Drops sentences naming a sensitive characteristic and masks emails and phone numbers."""
    kept = (piece.strip() for piece in _PIECES.split(text))
    return mask_contacts(
        " ".join(piece for piece in kept if piece and not mentions_sensitive(piece))
    )
