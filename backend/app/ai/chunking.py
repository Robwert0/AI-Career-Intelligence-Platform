from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TextChunk:
    section: str
    content: str
    chunk_index: int
