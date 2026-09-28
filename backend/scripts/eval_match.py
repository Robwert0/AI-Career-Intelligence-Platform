import argparse
import asyncio
import json
import statistics
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self, get_args

from pydantic import BaseModel, ConfigDict

from app.ai.embeddings import BgeEmbedder, Embedder
from app.ai.generation import GenerationResult, Message, SamplingSettings
from app.ai.match.dedup import merge_evidence
from app.ai.match.job_extract import extract_job
from app.ai.match.preselect import preselect
from app.ai.match.prompts import correction_message
from app.ai.match.requirements import requirement_refs
from app.ai.match.schemas import EvidenceItem, JobPosting, Requirement
from app.ai.match.structured import ExtractionError
from app.ai.ollama import OllamaGenerator
from app.core.config import settings
from app.core.redis import create_redis
from app.integrations.github import GitHubCache, GitHubClient
from app.schemas.match import AnalysisInput, RequirementStatus
from app.services.analysis_service import analyse
from app.services.analysis_sources import (
    Ready,
    SourcesState,
    decide,
    initial_sources,
    read_sources,
)
from app.services.candidate_evidence import CvReading, GitHubReading, read_cv, read_github

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CV = REPO_ROOT / "files" / "RobertMirea_CV2026.pdf"
EVAL_DIR = REPO_ROOT / "docs" / "eval"
DEFAULT_POSTINGS = EVAL_DIR / "postings"
DEFAULT_RESULTS = EVAL_DIR / "results"
STATUSES: tuple[str, ...] = get_args(RequirementStatus)
MIN_RELATED_POSTINGS = 5
CORRECTION_PREFIX = correction_message("").content.split("Problems:")[0]

# Off-domain on purpose: none of these should relate to a software engineer's evidence.
UNRELATED: dict[str, list[str]] = {
    "registered-nurse": [
        "Active registered nurse licence",
        "3 years of acute care nursing",
        "BLS and ACLS certification",
        "Experience administering medication and IV therapy",
    ],
    "truck-driver": [
        "Class A commercial driving licence",
        "Clean driving record for 3 years",
        "Able to lift 50 lbs",
        "Valid DOT medical card",
    ],
    "pastry-chef": [
        "5 years in a professional pastry kitchen",
        "Laminated dough and viennoiserie",
        "Food hygiene certificate",
        "Menu costing",
    ],
    "litigation-lawyer": [
        "Admitted to the bar",
        "5 years of commercial litigation",
        "Deposition and trial experience",
        "Legal research with Westlaw",
    ],
    "electrician": [
        "Journeyman electrician licence",
        "Commercial wiring and conduit bending",
        "Reading electrical blueprints",
        "OSHA 30 certification",
    ],
    "dental-hygienist": [
        "Registered dental hygienist licence",
        "Periodontal charting",
        "Local anaesthesia permit",
        "Dental radiography certification",
    ],
}


class LabelFile(BaseModel):
    """docs/eval/postings/<slug>.json: one real posting and Robert's status for each requirement."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    source_url: str | None = None
    posting: JobPosting
    labels: dict[str, str | None]
    notes: str = ""

    def checked(self) -> Self:
        ids = {ref.id for ref in requirement_refs(self.posting)}
        unknown = sorted(set(self.labels) - ids)
        if unknown:
            raise ValueError(f"{self.slug}: labels for requirements not in the posting: {unknown}")
        bad = sorted({v for v in self.labels.values() if v is not None and v not in STATUSES})
        if bad:
            raise ValueError(f"{self.slug}: unknown statuses {bad}; use one of {STATUSES}")
        return self

    def labelled(self) -> dict[str, str]:
        return {rid: status for rid, status in self.labels.items() if status is not None}

    def compared(self) -> dict[str, str]:
        """Labels worth comparing: a sensitive item is not_assessed by code, so it always agrees."""
        sensitive = {ref.id for ref in requirement_refs(self.posting) if ref.sensitive}
        return {rid: s for rid, s in self.labelled().items() if rid not in sensitive}


def template(slug: str, posting: JobPosting, source_url: str | None = None) -> LabelFile:
    return LabelFile(
        slug=slug,
        source_url=source_url,
        posting=posting,
        labels={
            ref.id: "not_assessed" if ref.sensitive else None for ref in requirement_refs(posting)
        },
    )


def load_label_files(directory: Path) -> list[LabelFile]:
    return [
        LabelFile.model_validate_json(path.read_text()).checked()
        for path in sorted(directory.glob("*.json"))
    ]


def suggested_threshold(related: Sequence[float], unrelated: Sequence[float]) -> float | None:
    """The midpoint between the two sets, or None when they overlap and no number divides them."""
    lowest_related, highest_unrelated = min(related), max(unrelated)
    if lowest_related <= highest_unrelated:
        return None
    return (lowest_related + highest_unrelated) / 2


@dataclass
class Tally:
    matches: int = 0
    labelled: int = 0
    confusion: Counter[tuple[str, str]] = field(default_factory=Counter)

    def add(self, labels: dict[str, str], predicted: dict[str, str]) -> None:
        for rid, label in labels.items():
            got = predicted.get(rid, "missing")
            self.labelled += 1
            self.matches += got == label
            self.confusion[(label, got)] += 1

    @property
    def agreement(self) -> float:
        return self.matches / self.labelled if self.labelled else 0.0


def flip_rate(runs: Sequence[dict[str, str]]) -> float:
    """The share of requirements whose status is not the same in every run."""
    ids = set().union(*runs) if runs else set()
    if not ids:
        return 0.0
    return sum(len({run.get(rid) for run in runs}) > 1 for rid in ids) / len(ids)


def rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


class CountingGenerator:
    """Wraps the real adapter to count calls and schema retries without touching app code."""

    def __init__(self, timeout_seconds: int) -> None:
        self._inner = OllamaGenerator(timeout_seconds=timeout_seconds)
        self.calls = 0
        self.retries = 0

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    async def generate(
        self,
        messages: list[Message],
        *,
        sampling: SamplingSettings | None = None,
        top_logprobs: int | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> GenerationResult:
        self.calls += 1
        self.retries += bool(messages) and messages[-1].content.startswith(CORRECTION_PREFIX)
        return await self._inner.generate(
            messages, sampling=sampling, top_logprobs=top_logprobs, response_schema=response_schema
        )

    async def aclose(self) -> None:
        await self._inner.aclose()


async def _stage(stage: str) -> None:
    return None


async def read_candidate(
    cv: Path, github_url: str | None, generator: CountingGenerator
) -> tuple[SourcesState, float]:
    request = AnalysisInput(
        posting=JobPosting(title="eval"), github_url=github_url, cv_provided=True
    )
    blobs = {"cv_file": cv.read_bytes()}
    redis = create_redis()
    token = settings.github_token.get_secret_value() if settings.github_token else None
    fetcher = GitHubClient(token=token)
    cache = GitHubCache(redis, ttl_seconds=settings.github_cache_ttl_seconds)

    async def take_cv(name: str) -> bytes | None:
        return blobs.pop(name, None)

    async def cv_source(*, file: bytes | None = None, text: str | None = None) -> CvReading:
        return await read_cv(file=file, text=text, generator=generator)

    async def github_source(url: str) -> GitHubReading:
        return await read_github(url, fetcher=fetcher, cache=cache)

    started = time.monotonic()
    try:
        state = await read_sources(
            initial_sources(request),
            take_cv=take_cv,
            read_cv=cv_source,
            read_github=github_source,
            on_stage=_stage,
        )
    finally:
        await redis.aclose()
    verdict = decide(state)
    if not isinstance(verdict, Ready):
        raise SystemExit(f"the candidate sources did not read cleanly: {verdict}")
    return state, time.monotonic() - started


def unrelated_postings(files: Sequence[LabelFile]) -> dict[str, JobPosting]:
    """The built-in off-domain postings, plus any real ones prepared into --unrelated."""
    built_in = {
        slug: JobPosting(title=slug, required=[Requirement(text=t, sensitive=False) for t in texts])
        for slug, texts in UNRELATED.items()
    }
    return {**built_in, **{f.slug: f.posting for f in files}}


def best_similarity(
    posting: JobPosting, evidence: Sequence[EvidenceItem], embedder: Embedder
) -> float:
    assessable = [ref for ref in requirement_refs(posting) if not ref.sensitive]
    return preselect(assessable, evidence, embedder, top_k=1).best_similarity


async def prepare(args: argparse.Namespace) -> int:
    generator = OllamaGenerator(timeout_seconds=settings.job_extract_generation_timeout_seconds)
    written = 0
    try:
        for text_file in sorted(args.postings.glob("*.txt")):
            target = text_file.with_suffix(".json")
            if target.exists():
                continue
            try:
                extraction = await extract_job(generator, text_file.read_text())
            except ExtractionError as exc:
                print(f"{text_file.name}: {exc.code}")
                continue
            target.write_text(
                template(text_file.stem, extraction.posting).model_dump_json(indent=2)
            )
            written += 1
            print(
                f"{target.name}: {len(extraction.posting.required)} required, "
                f"{len(extraction.posting.preferred)} preferred; label it before running"
            )
    finally:
        await generator.aclose()
    print(f"{written} template(s) written to {args.postings}")
    return 0


async def calibrate(args: argparse.Namespace) -> int:
    files = load_label_files(args.postings)
    if len(files) < MIN_RELATED_POSTINGS:
        print(
            f"need at least {MIN_RELATED_POSTINGS} postings in {args.postings}; run prepare first"
        )
        return 2
    generator = CountingGenerator(settings.evidence_extract_generation_timeout_seconds)
    try:
        state, _ = await read_candidate(args.cv, args.github, generator)
    finally:
        await generator.aclose()
    evidence = merge_evidence(state.cv.items, state.github.items)
    embedder = BgeEmbedder()
    related = {f.slug: best_similarity(f.posting, evidence, embedder) for f in files}
    extra = load_label_files(args.unrelated) if args.unrelated else []
    unrelated = {
        slug: best_similarity(posting, evidence, embedder)
        for slug, posting in unrelated_postings(extra).items()
    }
    for label, rows in (("RELATED", related), ("UNRELATED", unrelated)):
        for slug, similarity in sorted(rows.items(), key=lambda row: row[1]):
            print(f"{label}\t{similarity:.4f}\t{slug}")
    print(f"\nevidence items          {len(evidence)}")
    print(f"lowest  RELATED         {min(related.values()):.4f}")
    print(f"highest UNRELATED       {max(unrelated.values()):.4f}")
    suggested = suggested_threshold(list(related.values()), list(unrelated.values()))
    if suggested is None:
        print("\nNO CLEAN SEPARATION: the sets overlap, so no threshold divides them.")
        print("Record this as a finding and do not pick a number.")
        return 1
    print(f"\nsuggested MATCH_PRESELECT_MIN_SIMILARITY={suggested:.4f}")
    return 0


@dataclass
class RunRecord:
    slug: str
    run: int
    score: int | None
    statuses: dict[str, str]
    seconds: float
    cited: int
    dropped: int
    failure: str | None = None


async def _analyse_once(
    label: LabelFile,
    state: SourcesState,
    embedder: Embedder,
    assess_gen: CountingGenerator,
    recommend_gen: CountingGenerator,
    run: int,
    source_seconds: float,
) -> RunRecord:
    started = time.monotonic()
    try:
        outcome = await analyse(
            label.posting,
            state,
            embedder=embedder,
            assess_generator=assess_gen,
            recommend_generator=recommend_gen,
            on_stage=_stage,
            top_k=settings.match_preselect_top_k,
            min_similarity=settings.match_preselect_min_similarity,
        )
    except ExtractionError as exc:
        return RunRecord(label.slug, run, None, {}, time.monotonic() - started, 0, 0, exc.code)
    return RunRecord(
        slug=label.slug,
        run=run,
        score=outcome.report.score,
        statuses={r.id: r.status for r in outcome.report.requirements},
        seconds=source_seconds + time.monotonic() - started,
        cited=outcome.metrics.cited,
        dropped=outcome.metrics.dropped_citations,
        failure="refused" if outcome.metrics.refused else None,
    )


async def run_eval(args: argparse.Namespace) -> int:
    files = [f for f in load_label_files(args.postings) if f.compared()]
    if not files:
        print(f"no labelled postings in {args.postings}; label the templates first")
        return 2
    embedder = BgeEmbedder()
    evidence_gen = CountingGenerator(settings.evidence_extract_generation_timeout_seconds)
    assess_gen = CountingGenerator(settings.match_assess_generation_timeout_seconds)
    recommend_gen = CountingGenerator(settings.match_recommend_generation_timeout_seconds)
    records: list[RunRecord] = []
    try:
        for run in range(1, args.runs + 1):
            state, source_seconds = await read_candidate(args.cv, args.github, evidence_gen)
            for label in files:
                record = await _analyse_once(
                    label, state, embedder, assess_gen, recommend_gen, run, source_seconds
                )
                records.append(record)
                print(
                    f"run {run} {label.slug:30} score={record.score} "
                    f"{record.seconds:6.1f}s {record.failure or ''}"
                )
    finally:
        for generator in (evidence_gen, assess_gen, recommend_gen):
            await generator.aclose()
    summary = summarise(files, records, [evidence_gen, assess_gen, recommend_gen])
    print(json.dumps(summary, indent=2))
    args.results.mkdir(parents=True, exist_ok=True)
    out = args.results / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    out.write_text(
        json.dumps({"summary": summary, "runs": [r.__dict__ for r in records]}, indent=2)
    )
    print(f"written {out}")
    return 0


def summarise(
    files: Sequence[LabelFile],
    records: Sequence[RunRecord],
    generators: Sequence[CountingGenerator],
) -> dict[str, Any]:
    tally = Tally()
    by_slug: dict[str, list[RunRecord]] = {}
    for record in records:
        by_slug.setdefault(record.slug, []).append(record)
    for label in files:
        for record in by_slug.get(label.slug, []):
            tally.add(label.compared(), record.statuses)
    first_attempts = sum(g.calls - g.retries for g in generators)
    stability = {
        slug: {
            "scores": [r.score for r in runs],
            "score_range": (
                max(s for s in scores) - min(s for s in scores)
                if (scores := [r.score for r in runs if r.score is not None])
                else None
            ),
            "status_flip_rate": round(flip_rate([r.statuses for r in runs]), 3),
        }
        for slug, runs in by_slug.items()
    }
    seconds = [r.seconds for r in records if r.failure in (None, "refused")]
    return {
        "postings": len(files),
        "runs": len(records),
        "status_agreement": round(tally.agreement, 3),
        "labelled_requirement_runs": tally.labelled,
        "confusion": {f"{label}->{got}": n for (label, got), n in sorted(tally.confusion.items())},
        "invalid_json_rate": round(rate(sum(g.retries for g in generators), first_attempts), 3),
        "failed_analyses": sum(r.failure not in (None, "refused") for r in records),
        "hallucinated_citation_rate": round(
            rate(sum(r.dropped for r in records), sum(r.cited for r in records)), 3
        ),
        "seconds_per_analysis": {
            "median": round(statistics.median(seconds), 1) if seconds else None,
            "max": round(max(seconds), 1) if seconds else None,
        },
        "stability": stability,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Calibrate and evaluate the Job Match Analyzer against the real model.",
        epilog=(
            "Run from backend/. Put each real posting's text in docs/eval/postings/<slug>.txt, "
            "run `prepare`, then review each <slug>.json: fix the posting if the extraction is "
            "wrong, and set every label to demonstrated, partial, not_demonstrated, unmet or "
            "not_assessed (null = unlabelled). Nothing under docs/ is committed."
        ),
    )
    parser.add_argument("--postings", type=Path, default=DEFAULT_POSTINGS)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare", help="extract each .txt posting into a label template")
    for name in ("calibrate", "run"):
        sub = commands.add_parser(name)
        sub.add_argument("--cv", type=Path, default=DEFAULT_CV)
        sub.add_argument("--github", default=None, help="https://github.com/<user>, optional")
    commands.choices["calibrate"].add_argument(
        "--unrelated",
        type=Path,
        default=None,
        help="a directory of real off-domain postings, prepared like --postings",
    )
    commands.choices["run"].add_argument("--runs", type=int, default=3)
    commands.choices["run"].add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    args = parser.parse_args()
    handler = {"prepare": prepare, "calibrate": calibrate, "run": run_eval}[args.command]
    return asyncio.run(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
