import re

PHONE_PLACEHOLDER = "[phone redacted]"

# Nine digits covers Romanian and most European numbers while sparing year ranges ("2021-2025" is
# eight); 8-digit national numbers (Nordics, Singapore, Hong Kong) slip through. Only ASCII
# separators are matched and newlines are excluded so adjacent lines never merge. Tuned for the
# owner's CV: uploaded CVs (p5) need phonenumbers-grade matching instead.
_MIN_PHONE_DIGITS = 9
_NUMBER_RUN = re.compile(r"(?<![\w/])\(?\+?\d[\d \t().-]*\d(?!\w)")


def _redact(match: re.Match[str]) -> str:
    run = match.group()
    digits = sum(char.isdigit() for char in run)
    return PHONE_PLACEHOLDER if digits >= _MIN_PHONE_DIGITS else run


def redact_phone_numbers(text: str) -> str:
    return _NUMBER_RUN.sub(_redact, text)
