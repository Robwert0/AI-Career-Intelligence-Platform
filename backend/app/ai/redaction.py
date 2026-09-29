import re

# Heuristic, not phonenumbers-grade; uploaded CVs will hit its gaps.
PHONE_PLACEHOLDER = "[phone redacted]"

# Nine digits covers Romanian and most European numbers while sparing year ranges ("2021-2025" is
# eight). Only ASCII separators are matched and newlines are excluded so adjacent lines never
# merge.
_MIN_PHONE_DIGITS = 9
# An 8-digit national number (Nordics, Singapore, Hong Kong) is grouped by spaces ("12 34 56 78",
# "2345 6789") or, in Hong Kong, by a single hyphen ("2345-6789") — the same shape as a year
# range ("2021-2025"). Digit count and punctuation alone can't tell those apart; whether both
# halves are plausible years is the only signal available without a numbering-plan library.
_MIN_SPACED_PHONE_DIGITS = 8
_MIN_YEAR, _MAX_YEAR = 1950, 2035
_NUMBER_RUN = re.compile(r"(?<![\w/])\(?\+?\d[\d \t().-]*\d(?!\w)")
# A clean two-group shape only: "2345-6789" or "2021 - 2025", not a date bumped up against an
# unrelated later number by the dot-bridging that lets phone groups like "0700.000.000" match
# ("Last pushed 2026-08. 12 stars" must never become one run).
_HYPHENATED_PAIR = re.compile(r"^\(?\+?\s*(\d{4})\s*-\s*(\d{4})\s*\)?$")


def _hyphenated_pair(run: str) -> re.Match[str] | None:
    return _HYPHENATED_PAIR.fullmatch(run.strip())


def _is_year_range(pair: re.Match[str]) -> bool:
    first, second = int(pair.group(1)), int(pair.group(2))
    return _MIN_YEAR <= first <= _MAX_YEAR and _MIN_YEAR <= second <= _MAX_YEAR


def _redact(match: re.Match[str]) -> str:
    run = match.group()
    digits = sum(char.isdigit() for char in run)
    if digits >= _MIN_PHONE_DIGITS:
        return PHONE_PLACEHOLDER
    if digits >= _MIN_SPACED_PHONE_DIGITS:
        if " " in run and "-" not in run:
            return PHONE_PLACEHOLDER
        if "-" in run:
            pair = _hyphenated_pair(run)
            if pair is not None and not _is_year_range(pair):
                # Neither half reads as a plausible year, so a hyphen here is how a Hong Kong
                # number is grouped, not a date range. A real 8-digit number whose first half
                # happens to fall in 1950-2035 (rare, but possible) still slips through: that
                # gap is the trade-off of a punctuation heuristic instead of a numbering-plan
                # library.
                return PHONE_PLACEHOLDER
    return run


def redact_phone_numbers(text: str) -> str:
    return _NUMBER_RUN.sub(_redact, text)
