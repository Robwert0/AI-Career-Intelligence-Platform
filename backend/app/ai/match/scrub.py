import re

from app.ai.redaction import redact_phone_numbers

EMAIL_PLACEHOLDER = "[email redacted]"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Characteristics a match must never weigh (spec §5.4: age, gender, ethnicity, religion,
# nationality, marital/family status, health, disability, work authorisation/visa/citizenship,
# sexual orientation), plus identity numbers. A sentence that mentions one is dropped whole:
# masking only the value would still leave "Nationality: ___". Every term is either labelled
# (needs a colon or an anchoring word) or trailing-\b-bounded, so it never eats a real skill —
# audit M3 found bare "photo"/"disabled" doing exactly that ("Photoshop", "Disabled legacy
# endpoints"); bare "health"/"visa"/"race" would repeat the mistake ("healthcare", "Visa
# payment APIs", "race condition"), so those stay labelled or contextual.
_SENSITIVE = re.compile(
    r"\b(?:date\s+of\s+birth|d\.?o\.?b\b|birth\s*date|born\s+(?:on|in)\b|born\s+\d{4}"
    r"|place\s+of\s+birth|birthplace|\d{1,3}\s+years?\s+old|age\s*:|age\s*\d|y/?o\b"
    r"|marital|married|divorced|widowed|separated|spouse|\bwife\b|\bhusband\b|\bfianc[ée]e?\b"
    r"|\bchildren\b|\bkids\b|father\s+of|mother\s+of|\bdad\b|\bmum\b|\bmom\b"
    r"|nationality|citizenship|citizen\s+of|mother\s+tongue"
    r"|ethnic|race\s*:"
    r"|religio|\bmuslim\b|\bchristian\b|\bjewish\b|\bhindu\b|\bbuddhist\b|\batheist\b|\bsikh\b"
    r"|\bjain\b|\bmormon\b|\bevangelical\b"
    r"|gender|sex\s*:|pregnan|sexual\s+orientation|\btransgender\b|\bhomosexual\b"
    r"|\bheterosexual\b|\bbisexual\b|\blesbian\b|\bqueer\b|non-binary"
    r"|disabilit|disabled\s+(?:person|veteran|since|applicant)\b|health\s*:|medical\s+condition"
    r"|\bvisa\s+(?:status|sponsorship|require\w*|holder|application)|work\s+(?:permit"
    r"|authori[sz]ation)|right\s+to\s+work"
    r"|passport|national\s+id|id\s+number|identity\s+card|social\s+security|\bssn\b|\bcnp\b"
    r"|\bphotos?\b|\bphotograph\b"
    # Romanian equivalents: the owner's market is RO, and the CV/GitHub sources may be in it.
    r"|na[țt]ionalitate|cet[ăa][țt]enie|data\s+na[șs]terii|stare\s+civil[ăa]|religie)",
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
