import logging
import re
from collections import Counter
from dataclasses import dataclass

from app.ai.generation import Generator, SamplingSettings
from app.ai.input_guard import detect_injection_phrases
from app.ai.match.prompts import build_evidence_extract_messages
from app.ai.match.schemas import CvEntry, CvEntryKind, EvidenceItem, ExtractedCv
from app.ai.match.scrub import mask_contacts, mentions_sensitive, scrub_evidence_text
from app.ai.match.structured import ExtractionError, generate_validated

logger = logging.getLogger(__name__)

# About 8k tokens at a conservative 3 characters per token: with the prompt and a 6k-token
# reply it stays inside the 16k context window. Longer CVs are cut and the cut is reported.
MAX_CV_PROMPT_CHARS = 24_000
MAX_CV_ITEMS = 40
EVIDENCE_EXTRACT_SAMPLING = SamplingSettings(temperature=0.0, seed=0, max_output_tokens=6144)
MIN_GROUNDED_SHARE = 0.7
EVIDENCE_TEXT_CHARS = 600

_ID_SEGMENT: dict[CvEntryKind, str] = {
    "work": "experience",
    "project": "project",
    "skill_list": "skills",
    "education": "education",
    "accomplishment": "accomplishment",
}
_DEFAULT_LABEL: dict[CvEntryKind, str] = {
    "work": "Experience",
    "project": "Projects",
    "skill_list": "Skills",
    "education": "Education",
    "accomplishment": "Accomplishments",
}
_WORD = re.compile(r"[a-z0-9][a-z0-9+#]*")
_REPO_LINK = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100})"
)


@dataclass(frozen=True, slots=True)
class CvEvidence:
    items: tuple[EvidenceItem, ...]
    input_truncated: bool
    dropped: int


def _words(text: str) -> list[str]:
    return [word for word in _WORD.findall(text.lower()) if len(word) >= 2 or word.isdigit()]


def _grounded(entry: CvEntry, vocabulary: set[str]) -> bool:
    # The model may shorten an entry but not invent one: most of its words must be in the CV.
    words = _words(entry.text)
    if not words:
        return False
    return sum(word in vocabulary for word in words) / len(words) >= MIN_GROUNDED_SHARE


def repo_link(raw: str) -> str | None:
    match = _REPO_LINK.fullmatch(raw.strip().rstrip("/").removesuffix(".git"))
    if match is None:
        return None
    return f"https://github.com/{match.group(1).lower()}/{match.group(2).lower()}"


def _repo_links(entry: CvEntry, cv_text: str) -> tuple[str, ...]:
    found = (repo_link(link) for link in entry.links[:10] if link.strip() in cv_text)
    return tuple(dict.fromkeys(link for link in found if link is not None))


def _short_field(value: str | None) -> str | None:
    # Labels and names are never split into sentences: a sensitive one is dropped whole.
    if value is None or mentions_sensitive(value):
        return None
    return mask_contacts(value)[:120] or None


def _entry_name(label: str) -> str | None:
    _, separator, name = label.partition(" · ")
    return _short_field(name.strip()) if separator else None


async def extract_cv_evidence(generator: Generator, cv_text: str) -> CvEvidence:
    truncated = len(cv_text) > MAX_CV_PROMPT_CHARS
    text = cv_text[:MAX_CV_PROMPT_CHARS]
    flagged = detect_injection_phrases(text)
    if flagged:
        logger.warning("cv injection phrasing detected patterns=%s", ",".join(flagged))

    parsed = await generate_validated(
        generator, build_evidence_extract_messages(text), ExtractedCv, EVIDENCE_EXTRACT_SAMPLING
    )
    if not parsed.is_cv:
        raise ExtractionError("not_a_cv")

    vocabulary = set(_words(text))
    counters: Counter[str] = Counter()
    items: list[EvidenceItem] = []
    for entry in parsed.items[:MAX_CV_ITEMS]:
        body = scrub_evidence_text(entry.text)[:EVIDENCE_TEXT_CHARS]
        if not body or not _grounded(entry, vocabulary):
            continue
        segment = _ID_SEGMENT[entry.kind]
        items.append(
            EvidenceItem(
                id=f"cv:{segment}:{counters[segment]}",
                sources=("cv",),
                kind=entry.kind,
                section_label=_short_field(entry.section_label) or _DEFAULT_LABEL[entry.kind],
                name=_entry_name(entry.section_label),
                text=body,
                repo_links=_repo_links(entry, text),
            )
        )
        counters[segment] += 1

    dropped = len(parsed.items) - len(items)
    logger.info("cv evidence extracted items=%d dropped=%d", len(items), dropped)
    return CvEvidence(items=tuple(items), input_truncated=truncated, dropped=dropped)
