from dataclasses import dataclass

from app.core.sections import HEADING_ALIASES


@dataclass(frozen=True, slots=True)
class TextChunk:
    section: str
    content: str
    chunk_index: int


def chunk_cv(markdown: str) -> list[TextChunk]:
    chunk: list[TextChunk] = []
    index: int = 0
    for piece in markdown.split("\n## "):
        if not piece.strip():
            continue
        heading, _, _ = piece.partition("\n")
        key = " ".join(heading.split()).lower()
        section = HEADING_ALIASES.get(key, "other")
        chunk.append(TextChunk(section, piece, index))
        index += 1

    return chunk
