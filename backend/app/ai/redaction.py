import re

PHONE_PLACEHOLDER = "[phone redacted]"

# Nine digits covers Romanian and most European numbers while sparing year ranges ("2021-2025" is
# eight). Only ASCII separators are matched and newlines are excluded so adjacent lines never
# merge.
_MIN_PHONE_DIGITS = 9
# An 8-digit national number (Nordics, Singapore, Hong Kong) is grouped by spaces, never by a
# hyphen: "12 34 56 78", "2345 6789". A hyphen at 8 digits is always a date or version range in
# CV text ("2021-2025", "2021 - 2025", "6-DOF"), so it is excluded from this narrower rule.
_MIN_SPACED_PHONE_DIGITS = 8
_NUMBER_RUN = re.compile(r"(?<![\w/])\(?\+?\d[\d \t().-]*\d(?!\w)")


def _redact(match: re.Match[str]) -> str:
    run = match.group()
    digits = sum(char.isdigit() for char in run)
    if digits >= _MIN_PHONE_DIGITS:
        return PHONE_PLACEHOLDER
    if digits >= _MIN_SPACED_PHONE_DIGITS and " " in run and "-" not in run:
        return PHONE_PLACEHOLDER
    return run


def redact_phone_numbers(text: str) -> str:
    return _NUMBER_RUN.sub(_redact, text)
