import re

PATTERNS: dict[str, re.Pattern[str]] = {
    "override_instructions": re.compile(
        r"\b(ignore|disregard|forget|override)\b[^.?!]{0,40}?\b"
        r"(previous|prior|above|earlier|all|any)\b[^.?!]{0,25}?\b"
        r"(instruction|direction|prompt|rule|command|guideline)",
        re.IGNORECASE,
    ),
    "reveal_prompt": re.compile(
        r"\b(reveal|repeat|print|show|output|display|tell me|what are)\b[^.?!]{0,30}?\b"
        r"(your|the)\b[^.?!]{0,25}?\b"
        r"(system prompt|initial instruction|original instruction|instructions)",
        re.IGNORECASE,
    ),
    "role_override": re.compile(
        r"\byou are (now|no longer)\b|\bact as (if|though|an?)\b|\bpretend (to be|you are)\b",
        re.IGNORECASE,
    ),
}


def detect_injection_phrases(text: str) -> tuple[str, ...]:
    return tuple(name for name, pattern in PATTERNS.items() if pattern.search(text))
