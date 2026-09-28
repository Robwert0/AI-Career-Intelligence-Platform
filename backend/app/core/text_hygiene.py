import unicodedata


def strip_invisible_unicode(text: str) -> str:
    """NFKC-normalises, then drops every Unicode format-control (category Cf) character.

    That category covers zero-width joiners/spaces (U+200B-U+200D, U+2060), bidi overrides
    (U+202A-U+202E, U+2066-U+2069) and the Unicode Tag block (U+E0000-U+E007F) used for "ASCII
    smuggling" — a model can read tag-encoded instructions that a human reviewer and
    detect_injection_phrases never see, since none of these characters render visibly.
    """
    normalised = unicodedata.normalize("NFKC", text)
    return "".join(char for char in normalised if unicodedata.category(char) != "Cf")
