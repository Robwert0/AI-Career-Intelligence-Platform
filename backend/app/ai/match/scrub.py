import re

from app.ai.match.text_limits import SEGMENT_BOUNDARY
from app.ai.redaction import redact_phone_numbers
from app.core.text_hygiene import strip_invisible_unicode

EMAIL_PLACEHOLDER = "[email redacted]"
URL_PLACEHOLDER = "[profile link redacted]"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# "john at gmail dot com": a name-shaped token, " at ", a domain-shaped token, then one or more
# " dot " groups, so multi-part domains ("some dot co dot uk") are still masked whole.
_OBFUSCATED_EMAIL = re.compile(
    r"\b[\w.+-]+\s+(?:at|\[at\]|\(at\))\s+[\w-]+(?:\s+(?:dot|\[dot\]|\(dot\))\s+[\w-]+)+\b",
    re.IGNORECASE,
)
# Social/professional profile links carry the same identifying weight as an address; github.com
# is the one exception, because a repo URL is a work artefact, not a personal contact channel,
# and evidence text can legitimately reference one (a README linking to a related project).
# dedup.py never reads this scrubbed text; it matches on EvidenceItem.url/repo_links, which are
# taken straight from the unscrubbed CV text and the GitHub API.
_PROFILE_URL = re.compile(
    r"\b(?:https?://)?(?:www\.)?(?:linkedin|twitter|x|facebook|instagram)\.com(?:/\S*)?",
    re.IGNORECASE,
)
# A sentence that opens with one of these labels is a contact line in its own right (an address,
# a phone or social handle): drop it whole rather than only masking the value inside it.
_CONTACT_LABEL = re.compile(
    r"^(?:address|adresa|tel|telefon|phone|mobile|email|e-mail|linkedin)\s*:?\s",
    re.IGNORECASE,
)
# Characteristics a match must never weigh (spec §5.4: age, gender, ethnicity, religion,
# nationality, marital/family status, health, disability, work authorisation/visa/citizenship,
# sexual orientation), plus identity numbers. A sentence that mentions one is dropped whole:
# masking only the value would still leave "Nationality: ___". No bare term here is proven
# collision-free: each was checked against realistic CV phrasing (a real auth library named
# "Passport.js", "separated the monolith", WCAG/accessibility work, a "children's" product, a
# "gender classification" model all turned up real false positives and are now excluded), but a
# labelled or anchored form only narrows the risk, it doesn't remove it.
_SENSITIVE = re.compile(
    r"\b(?:date\s+of\s+birth|d\.?o\.?b\b|birth\s*date|born\s+(?:on|in)\b|born\s+\d{4}"
    r"|place\s+of\s+birth|birthplace|\d{1,3}\s+years?\s+old|age\s*:|age\s*\d|y/?o\b"
    r"|marital|married|divorced|widowed|spouse|\bwife\b|\bhusband\b|\bfianc[ée]e?\b"
    r"|(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+child(?:ren)?\b"
    r"|\bkids\b|father\s+of|mother\s+of|\bdad\b|\bmum\b|\bmom\b"
    r"|nationality|citizenship|citizen\s+of|mother\s+tongue"
    r"|ethnic|race\s*:"
    r"|religio|\bmuslim\b|\bchristian\b|\bjewish\b|\bhindu\b|\bbuddhist\b|\batheist\b|\bsikh\b"
    r"|\bjain\b|\bmormon\b|\bevangelical\b"
    r"|gender\s*:|sex\s*:|pregnan|sexual\s+orientation|\btransgender\b|\bhomosexual\b"
    r"|\bheterosexual\b|\bbisexual\b|\blesbian\b|\bqueer\b|non-binary"
    r"|disabilit(?:y|ies)\s*(?::|status)|disabled\s+(?:person|veteran|since|applicant)\b"
    r"|health\s*:|medical\s+condition"
    r"|\bvisa\s+(?:status|sponsorship|require\w*|holder|application)|work\s+(?:permit"
    r"|authori[sz]ation)|right\s+to\s+work"
    r"|passport\s+(?:number|no\.?|#)|national\s+id|id\s+number|identity\s+card"
    r"|social\s+security|\bssn\b|\bcnp\b|\bphotos?\b|\bphotograph\b"
    # Romanian equivalents: the owner's market is RO, and the CV/GitHub sources may be in it.
    r"|na[țt]ionalitate|cet[ăa][țt]enie|data\s+na[șs]terii|stare\s+civil[ăa]|religie)",
    re.IGNORECASE,
)


def mentions_sensitive(text: str) -> bool:
    return _SENSITIVE.search(text) is not None


def mask_contacts(text: str) -> str:
    text = _OBFUSCATED_EMAIL.sub(EMAIL_PLACEHOLDER, text)
    text = _EMAIL.sub(EMAIL_PLACEHOLDER, text)
    text = _PROFILE_URL.sub(URL_PLACEHOLDER, text)
    return redact_phone_numbers(text).strip()


def scrub_evidence_text(text: str) -> str:
    """Drops sentences naming a sensitive characteristic and masks emails and phone numbers."""
    text = strip_invisible_unicode(text)
    kept = (piece.strip() for piece in SEGMENT_BOUNDARY.split(text))
    return mask_contacts(
        " ".join(
            piece
            for piece in kept
            if piece and not mentions_sensitive(piece) and not _CONTACT_LABEL.match(piece)
        )
    )
