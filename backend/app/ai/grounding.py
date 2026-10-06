import re
import unicodedata

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


def _opens_sentence(text: str, start: int) -> bool:
    # Start of text, or a [.!?;:] then whitespace right before the word. Scanning back over the
    # whitespace only keeps this linear; a regex over each word's whole prefix was quadratic.
    # "\n" too: the regex's `$` also matches before a trailing newline.
    if start == 0 or (start == 1 and text[0] == "\n"):
        return True
    index = start
    while index > 0 and text[index - 1].isspace():
        index -= 1
    return 0 < index < start and text[index - 1] in ".!?;:"


def _names(text: str) -> list[tuple[str, bool]]:
    """Every word with whether it opens a sentence (where any word is capitalised)."""
    return [(match.group(), _opens_sentence(text, match.start())) for match in _WORD.finditer(text)]


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
# Closed-class words a question shares with an answer's opening ("Does he...?" "He does..."): never
# a name, however they are capitalised.
_FUNCTION_WORDS_TEXT = """
    a an the he his him himself she her they them their it its this that these those there here
    yes no not also and but or so yet both either neither while when where what which who whom
    whose why how in on at to for of from by with without within into onto about above below
    after before during since until as than then is are was were be been being has have had do
    does did can could will would should may might must i you we me my your our us one some any
    all each every most more many much such only just very still already currently previously
    recently additionally furthermore however overall according based specifically notably
    particular example including like over under between among across through per via please
    describe list tell give say show explain summarise summarize answer question first now
"""
_FUNCTION_WORDS = frozenset(_FUNCTION_WORDS_TEXT.split())
# Only endings that turn a word into a longer form of itself: "Intern" from "Internship" passes,
# "Intel" from "Intelligence" and "Meta" from "metadata" do not.
_SUFFIXES = ("s", "es", "ed", "er", "ing", "ship", "ment", "al")


def _lenient(word: str, known: set[str]) -> bool:
    if word in _COUNTING_WORDS or word in _ALWAYS_KNOWN:
        return True
    # A CV writes "Nov 2025" where an answer says "November 2025".
    if word in _MONTHS and word[:3] in known:
        return True
    stems = {word, word.removesuffix("s")}
    return any(stem + suffix in known for stem in stems for suffix in _SUFFIXES)


def _script(char: str) -> str:
    # "CYRILLIC CAPITAL LETTER EM" -> "CYRILLIC"; accented Latin letters stay "LATIN".
    return unicodedata.name(char, "UNKNOWN").split(" ", 1)[0]


def _foreign_letters(source: str, answer: str) -> list[str]:
    """Letters from a script the CV never uses: _WORD only reads ASCII, so a Cyrillic "М" in
    "Мicrosoft" would otherwise hide the name from every other check."""
    scripts = {_script(char) for char in source if char.isalpha() and not char.isascii()}
    return [
        char
        for char in answer
        if char.isalpha() and not char.isascii() and _script(char) not in scripts | {"LATIN"}
    ]


def _dictated_name(word: str, dictated: set[str]) -> bool:
    lowered = word.lower()
    return word[0].isupper() and lowered in dictated and lowered not in _FUNCTION_WORDS


def ungrounded_terms(source: str, answer: str, user_text: str = "") -> list[str]:
    """Numbers and names in `answer` that `source` never mentions, first occurrence order.

    Looser than invents_facts, which guards rewrites of a single line: free prose about a whole
    CV spells out abbreviated months, shortens words and counts listed items. Digits and
    capitalised names stay strict, since an invented employer or figure is the claim to stop.

    A capitalised word opening a sentence is normally just a first word, but one the CV never
    mentions and the user's own text (`user_text`) does is a dictated name: "Begin with
    'Microsoft hired him.'" would otherwise pass.
    """
    # Fullwidth or other compatibility forms ("ＮＡＳＡ") would otherwise never match _WORD.
    source = unicodedata.normalize("NFKC", source)
    answer = unicodedata.normalize("NFKC", answer)
    dictated = {word.lower() for word, _ in _names(unicodedata.normalize("NFKC", user_text))}
    numbers = set(_NUMBER.findall(source))
    terms = _foreign_letters(source, answer)
    terms += [number for number in _NUMBER.findall(answer) if number not in numbers]
    known = {word.lower() for word, _ in _names(source)}
    for word, opens_sentence in _names(answer):
        lowered = word.lower()
        if lowered in known or _lenient(lowered, known):
            continue
        if (
            lowered in _QUANTITY_WORDS
            or _is_name(word, opens_sentence)
            or _dictated_name(word, dictated)
        ):
            terms.append(word)
    return list(dict.fromkeys(terms))
