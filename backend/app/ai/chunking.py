from dataclasses import dataclass

from app.ai.tokenizer import count_tokens, token_budget
from app.core.sections import HEADING_ALIASES

_SEPARATORS = ["\n\n", ". ", " "]


@dataclass(frozen=True, slots=True)
class TextChunk:
    section: str
    content: str
    chunk_index: int


def _pack(units: list[str], separators: list[str], budget: int) -> list[str]:
    current: list[str] = []
    groups: list[str] = []
    joiner = separators[0]
    for unit in units:
        if count_tokens(unit) > budget:
            if current:
                groups.append(joiner.join(current))
                current = []

            if len(separators) > 1:
                finer = separators[1:]
                pieces = unit.split(finer[0])
                groups.extend(_pack(pieces, finer, budget))
            else:
                groups.append(unit)

            continue

        candidate = joiner.join([*current, unit])
        if current and count_tokens(candidate) > budget:
            groups.append(joiner.join(current))
            current = [unit]
        else:
            current.append(unit)

    if current:
        groups.append(joiner.join(current))

    return groups


def chunk_cv(markdown: str) -> list[TextChunk]:
    chunk: list[TextChunk] = []
    for piece in markdown.split("\n## "):
        if not piece.strip():
            continue
        heading, _, _ = piece.partition("\n")
        key = " ".join(heading.split()).lower()
        section = HEADING_ALIASES.get(key, "other")

        heading_reserve = count_tokens(heading) + 1
        budget = token_budget() - heading_reserve
        paragraphs = piece.split(_SEPARATORS[0])
        groups = _pack(paragraphs, _SEPARATORS, budget)

        for position, group in enumerate(groups):
            if position:
                group = heading + "\n" + group
            chunk.append(TextChunk(section, group, len(chunk)))

    return chunk
