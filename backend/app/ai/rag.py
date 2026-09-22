import asyncio
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from app.ai.generation import GenerationResult, Generator, Message, SamplingSettings
from app.ai.input_guard import detect_injection_phrases
from app.ai.output_guard import validate_output
from app.ai.prompts import REFUSAL_TEXT, build_messages
from app.ai.retriever import EmptyQueryError, Retriever
from app.core.config import settings
from app.models import Chunk

logger = logging.getLogger(__name__)

RetrieverScope = Callable[[], AbstractAsyncContextManager[Retriever]]


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

    async def answer(self, question: str) -> Answer:
        flagged = detect_injection_phrases(question)
        if flagged:
            logger.warning("chat injection phrasing detected: %s", ",".join(flagged))

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
                "chat refused before generation best_similarity=%.4f text_hits=%d",
                result.best_similarity,
                result.text_hit_count,
            )
            return Answer(text=REFUSAL_TEXT, refused=True, sources=[])

        generated = await self._generate(build_messages(question, result.chunks))

        verdict = validate_output(generated)
        if not verdict.ok:
            logger.error(
                "chat output rejected check=%s model=%s text=%r",
                verdict.failed_check,
                generated.model,
                generated.text[:200],
            )
            return Answer(text=REFUSAL_TEXT, refused=True, sources=[])

        logger.info(
            "chat answered model=%s prompt_tokens=%d completion_tokens=%d latency_ms=%d",
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
