import re

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_MAGNITUDE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:k|m|bn|b|x|%)(?![a-z])", re.IGNORECASE)
_QUANTITY_WORDS = frozenset(
    [
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
        "thirty",
        "forty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
        "hundred",
        "hundreds",
        "thousand",
        "thousands",
        "million",
        "millions",
        "billion",
        "billions",
        "dozen",
        "dozens",
        "half",
        "twice",
        "thrice",
        "double",
        "doubled",
        "doubling",
        "triple",
        "tripled",
        "tripling",
        "quadrupled",
        "tenfold",
    ]
)
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.]*[A-Za-z0-9+#]|[A-Za-z]")
_SENTENCE_START = re.compile(r"(?:^|[.!?;:]\s+)$")


def _names(text: str) -> list[tuple[str, bool]]:
    """Every word with whether it opens a sentence (where any word is capitalised)."""
    return [
        (match.group(), bool(_SENTENCE_START.search(text[: match.start()])))
        for match in _WORD.finditer(text)
    ]


def _is_name(word: str, opens_sentence: bool) -> bool:
    # A capital mid-sentence is a name; at a sentence start only an inner capital or a digit
    # ("PostgreSQL", "GraphQL", "AWS", "S3") marks one, since any first word is capitalised.
    if any(char.isdigit() for char in word) or sum(char.isupper() for char in word) > 1:
        return True
    return word[0].isupper() and not opens_sentence


def invents_facts(before: str, after: str) -> bool:
    """True when `after` states a number, quantity or name that `before` does not contain."""
    if not set(_NUMBER.findall(after)) <= set(_NUMBER.findall(before)):
        return True
    magnitude = {m.lower().replace(" ", "") for m in _MAGNITUDE.findall(after)}
    if not magnitude <= {m.lower().replace(" ", "") for m in _MAGNITUDE.findall(before)}:
        return True
    known = {word.lower() for word, _ in _names(before)}
    for word, opens_sentence in _names(after):
        lowered = word.lower()
        if lowered in known:
            continue
        if lowered in _QUANTITY_WORDS or _is_name(word, opens_sentence):
            return True
    return False


# Counting items the CV lists ("two internships") is ordinary prose; larger quantity words are
# not, and stay unknown unless the CV uses them.
_COUNTING_WORDS = frozenset(
    ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "twice"]
)
_MONTHS = frozenset(
    [
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    ]
)
_ALWAYS_KNOWN = frozenset(["cv"])
_MIN_STEM = 4


def _lenient(word: str, known: set[str]) -> bool:
    if word in _COUNTING_WORDS or word in _ALWAYS_KNOWN:
        return True
    # A CV writes "Nov 2025" where an answer says "November 2025".
    if word in _MONTHS and word[:3] in known:
        return True
    # "Intern" from "Internship": a shortened CV word, never a new name.
    stem = word.removesuffix("s")
    return len(stem) >= _MIN_STEM and any(other.startswith(stem) for other in known)


def ungrounded_terms(source: str, answer: str) -> list[str]:
    """Numbers and names in `answer` that `source` never mentions, first occurrence order.

    Looser than invents_facts, which guards rewrites of a single line: free prose about a whole
    CV spells out abbreviated months, shortens words and counts listed items. Digits and
    capitalised names stay strict, since an invented employer or figure is the claim to stop.
    """
    numbers = set(_NUMBER.findall(source))
    terms = [number for number in _NUMBER.findall(answer) if number not in numbers]
    known = {word.lower() for word, _ in _names(source)}
    for word, opens_sentence in _names(answer):
        lowered = word.lower()
        if lowered in known or _lenient(lowered, known):
            continue
        if lowered in _QUANTITY_WORDS or _is_name(word, opens_sentence):
            terms.append(word)
    return list(dict.fromkeys(terms))
