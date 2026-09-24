import asyncio
import hashlib
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from app.ai.generation import GenerationResult, Generator, Message, SamplingSettings
from app.ai.input_guard import detect_injection_phrases
from app.ai.output_guard import validate_output
from app.ai.prompts import INCOMPLETE_TEXT, REFUSAL_TEXT, build_messages
from app.ai.retriever import EmptyQueryError, Retriever
from app.core.config import settings
from app.models import Chunk

logger = logging.getLogger(__name__)

RetrieverScope = Callable[[], AbstractAsyncContextManager[Retriever]]

# canary and ngram mean a suspected prompt leak, so the response must be indistinguishable from a
# refusal. empty and truncated are ordinary faults and get an honest message instead.
LEAK_CHECKS = frozenset({"canary", "ngram"})


class GenerationCapacityError(Exception):
    """Every generation slot is occupied; the same request may succeed once one frees up."""


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    refused: bool
    sources: list[Chunk]


class RagPipeline:
    def __init__(
        self,
        retriever_scope: RetrieverScope,
        generator: Generator,
        slots: asyncio.Semaphore,
    ) -> None:
        self._retriever_scope = retriever_scope
        self._generator = generator
        self._slots = slots

    async def answer(self, question: str, *, user_id: str | None = None) -> Answer:
        flagged = detect_injection_phrases(question)
        if flagged:
            logger.warning(
                "chat injection phrasing detected user=%s patterns=%s",
                user_id,
                ",".join(flagged),
            )

        try:
            async with self._retriever_scope() as retriever:
                result = await retriever.retrieve(
                    question,
                    document_id=settings.cv_document_id,
                    limit=settings.retrieval_limit,
                )
        except EmptyQueryError:
            return Answer(text=REFUSAL_TEXT, refused=True, sources=[])

        if result.best_similarity < settings.retrieval_similarity_threshold:
            logger.info(
                "chat refused before generation user=%s best_similarity=%.4f text_hits=%d",
                user_id,
                result.best_similarity,
                result.text_hit_count,
            )
            return Answer(text=REFUSAL_TEXT, refused=True, sources=[])

        generated = await self._generate(build_messages(question, result.chunks))

        verdict = validate_output(generated)
        if verdict.failed_check in LEAK_CHECKS:
            logger.error(
                "chat output rejected user=%s check=%s model=%s text_sha256=%s len=%d",
                user_id,
                verdict.failed_check,
                generated.model,
                hashlib.sha256(generated.text.encode()).hexdigest()[:16],
                len(generated.text),
            )
            return Answer(text=REFUSAL_TEXT, refused=True, sources=[])

        if not verdict.ok:
            logger.warning(
                "chat answer incomplete user=%s check=%s model=%s",
                user_id,
                verdict.failed_check,
                generated.model,
            )
            return Answer(text=INCOMPLETE_TEXT, refused=True, sources=[])

        logger.info(
            "chat answered user=%s model=%s prompt_tokens=%d completion_tokens=%d latency_ms=%d",
            user_id,
            generated.model,
            generated.usage.prompt_tokens,
            generated.usage.completion_tokens,
            generated.latency_ms,
        )

        return Answer(text=generated.text, refused=False, sources=result.chunks)

    async def _generate(self, messages: list[Message]) -> GenerationResult:
        try:
            async with asyncio.timeout(settings.chat_queue_timeout_seconds):
                await self._slots.acquire()
        except TimeoutError:
            logger.warning("chat rejected: every generation slot busy")
            raise GenerationCapacityError("no generation slot became free in time") from None

        try:
            return await self._generator.generate(
                messages,
                sampling=SamplingSettings(
                    temperature=settings.chat_temperature,
                    max_output_tokens=settings.chat_max_output_tokens,
                ),
            )
        finally:
            self._slots.release()
