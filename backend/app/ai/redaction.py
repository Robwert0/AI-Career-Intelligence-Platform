import re

PHONE_PLACEHOLDER = "[phone redacted]"

# Nine digits is shorter than any international or national mobile number and longer than any
# year range ("2021-2025" is eight). Separators exclude newlines so adjacent lines never merge.
_MIN_PHONE_DIGITS = 9
_NUMBER_RUN = re.compile(r"(?<![\w/])\(?\+?\d[\d \t().-]*\d(?!\w)")


def _redact(match: re.Match[str]) -> str:
    run = match.group()
    digits = sum(char.isdigit() for char in run)
    return PHONE_PLACEHOLDER if digits >= _MIN_PHONE_DIGITS else run


def redact_phone_numbers(text: str) -> str:
    return _NUMBER_RUN.sub(_redact, text)
