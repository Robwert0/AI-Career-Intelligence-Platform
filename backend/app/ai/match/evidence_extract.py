import logging
import re
from collections import Counter
from dataclasses import dataclass

from pydantic import ValidationError

from app.ai.generation import Generator, SamplingSettings
from app.ai.input_guard import detect_injection_phrases
from app.ai.match.prompts import build_evidence_extract_messages
from app.ai.match.schemas import CvEntry, CvEntryKind, EvidenceItem, ExtractedCv
from app.ai.match.scrub import mask_contacts, mentions_sensitive, scrub_evidence_text
from app.ai.match.structured import ExtractionError, generate_validated
from app.ai.match.text_limits import SEGMENT_BOUNDARY, cap_text
from app.integrations.github import GitHubProfile, GitHubRepo, GitHubSnapshot

logger = logging.getLogger(__name__)

# About 8k tokens at a conservative 3 characters per token: with the prompt and a 6k-token
# reply, this fits the default 16k GENERATION_CONTEXT_TOKENS but not the 8192-token floor
# Settings still allows — a deployment running at that floor needs a smaller cap or a bigger
# window. Longer CVs are cut and the cut is reported.
MAX_CV_PROMPT_CHARS = 24_000
# Same 2x ratio as job_extract's own byte cap (30_000 chars / 60_000 bytes): a non-ASCII
# character can take several bytes, so a character cap alone doesn't bound the payload size.
MAX_CV_PROMPT_BYTES = 48_000
MAX_CV_ITEMS = 40
EVIDENCE_EXTRACT_SAMPLING = SamplingSettings(temperature=0.0, seed=0, max_output_tokens=6144)
MIN_GROUNDED_SHARE = 0.7
# Bag-of-words grounding alone accepts a fabrication that recombines real CV words into a new
# claim: every word of "principal engineer led team of 5 people for 2 months" can be a real CV
# word without the CV ever saying that. Contiguous bigrams, built per sentence so a splice
# can't bridge two unrelated ones, catch the seam the recombination leaves behind.
MIN_GROUNDED_NGRAM_SHARE = 0.7
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


def _bigrams(words: list[str]) -> list[tuple[str, str]]:
    return list(zip(words, words[1:], strict=False))


def _cv_bigrams(cv_text: str) -> set[tuple[str, str]]:
    grams: set[tuple[str, str]] = set()
    for segment in SEGMENT_BOUNDARY.split(cv_text):
        grams.update(_bigrams(_words(segment)))
    return grams


def _grounded(entry: CvEntry, vocabulary: set[str], cv_bigrams: set[tuple[str, str]]) -> bool:
    # The model may shorten an entry but not invent one: most of its words must be in the CV,
    # and (when there are enough of them) most of its adjacent word pairs must be adjacent in
    # the CV too — a fabrication built from real CV words in a new order breaks that adjacency
    # at the seam, even though every individual word is genuine.
    words = _words(entry.text)
    if not words:
        return False
    if sum(word in vocabulary for word in words) / len(words) < MIN_GROUNDED_SHARE:
        return False
    grams = _bigrams(words)
    if not grams:
        return True
    return sum(gram in cv_bigrams for gram in grams) / len(grams) >= MIN_GROUNDED_NGRAM_SHARE


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
    text, truncated = cap_text(
        cv_text, max_chars=MAX_CV_PROMPT_CHARS, max_bytes=MAX_CV_PROMPT_BYTES
    )
    flagged = detect_injection_phrases(text)
    if flagged:
        logger.warning("cv injection phrasing detected patterns=%s", ",".join(flagged))

    parsed = await generate_validated(
        generator, build_evidence_extract_messages(text), ExtractedCv, EVIDENCE_EXTRACT_SAMPLING
    )
    if not parsed.is_cv:
        raise ExtractionError("not_a_cv")

    vocabulary = set(_words(text))
    cv_bigrams = _cv_bigrams(text)
    counters: Counter[str] = Counter()
    items: list[EvidenceItem] = []
    for entry in parsed.items[:MAX_CV_ITEMS]:
        body = scrub_evidence_text(entry.text)[:EVIDENCE_TEXT_CHARS]
        if not body or not _grounded(entry, vocabulary, cv_bigrams):
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


_README_NOISE = re.compile(
    r"```.*?```|<[^>]+>|!\[[^\]]*\]\([^)]*\)|^\s{0,3}#{1,6}\s*|^\s*[-*>]\s+",
    re.DOTALL | re.MULTILINE,
)
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def clip_text(text: str, limit: int = EVIDENCE_TEXT_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _readme_summary(readme: str) -> str:
    return " ".join(_MARKDOWN_LINK.sub(r"\1", _README_NOISE.sub(" ", readme)).split())


def _languages(languages: dict[str, int]) -> str:
    total = sum(languages.values())
    if total <= 0:
        return ""
    shares = sorted(((100 * size / total, name) for name, size in languages.items()), reverse=True)
    return ", ".join(f"{name} {round(share)}%" for share, name in shares[:5] if share >= 1)


def _repo_item(repo: GitHubRepo) -> EvidenceItem | None:
    parts = [f"{repo.name}: {repo.description}" if repo.description else repo.name]
    if languages := _languages(repo.languages):
        parts.append(f"Languages: {languages}")
    if repo.topics:
        parts.append(f"Topics: {', '.join(repo.topics)}")
    if repo.pushed_at:
        parts.append(f"Last pushed {repo.pushed_at[:7]}")
    if repo.stars:
        parts.append(f"{repo.stars} stars")
    if repo.readme and (summary := _readme_summary(repo.readme)):
        parts.append(f"README: {summary}")
    text = clip_text(scrub_evidence_text(". ".join(part.rstrip(". ") for part in parts)))
    if not text:
        # Every fact about this repo was sensitive (M2): a bare repo name is never itself
        # sensitive unless the name is, so fall back to it rather than crashing on an empty
        # EvidenceText, and drop the repo outright in that one case.
        fallback = f"GitHub repository {repo.name}"
        if mentions_sensitive(fallback):
            return None
        text = fallback
    try:
        return EvidenceItem(
            id=f"gh:repo:{repo.name.lower()}",
            sources=("github",),
            kind="repo",
            section_label=clip_text(f"GitHub · {repo.name}", 120),
            name=repo.name[:120],
            text=text,
            url=repo.url,
        )
    except ValidationError:
        return None


def _profile_item(profile: GitHubProfile) -> EvidenceItem | None:
    facts = [profile.bio, f"Company: {profile.company}" if profile.company else None]
    about = scrub_evidence_text(". ".join(fact.rstrip(". ") for fact in facts if fact))
    if not about:
        return None
    who = profile.name or profile.login
    text = f"GitHub profile of {who}. {about}. {profile.public_repos} public repositories."
    try:
        return EvidenceItem(
            id="gh:profile",
            sources=("github",),
            kind="profile",
            section_label="GitHub · profile",
            name=profile.login[:120],
            text=clip_text(mask_contacts(text)),
        )
    except ValidationError:
        return None


def github_evidence(snapshot: GitHubSnapshot) -> tuple[EvidenceItem, ...]:
    """Deterministic: the same snapshot always yields the same items, with no model involved."""
    repos = [item for repo in snapshot.repos if (item := _repo_item(repo)) is not None]
    profile = _profile_item(snapshot.profile)
    return tuple([profile, *repos] if profile is not None else repos)
