import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

from app.ai.conversation import CONDENSE_SAMPLING, Turn, fallback_query, standalone_from
from app.ai.embeddings import QueryTooLongError
from app.ai.generation import GenerationResult, Generator, Message, SamplingSettings
from app.ai.grounding import ungrounded_terms
from app.ai.input_guard import detect_injection_phrases
from app.ai.output_guard import validate_output
from app.ai.prompts import (
    INCOMPLETE_TEXT,
    REFUSAL_TEXT,
    build_condense_messages,
    build_messages,
)
from app.ai.retriever import EmptyQueryError, RetrievalResult, Retriever
from app.core.config import settings
from app.models import Chunk

logger = logging.getLogger(__name__)

RetrieverScope = Callable[[], AbstractAsyncContextManager[Retriever]]

# canary and ngram mean a suspected prompt leak, so the response must be indistinguishable from a
# refusal. empty and truncated are ordinary faults and get an honest message instead.
LEAK_CHECKS = frozenset({"canary", "ngram"})


def _is_refusal(text: str) -> bool:
    return text.strip().rstrip(".").casefold() == REFUSAL_TEXT.rstrip(".").casefold()


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

    async def answer(
        self, question: str, *, history: Sequence[Turn] = (), user_id: str | None = None
    ) -> Answer:
        flagged = sorted(
            {
                pattern
                for text in (question, *(turn.content for turn in history))
                for pattern in detect_injection_phrases(text)
            }
        )
        if flagged:
            logger.warning(
                "chat injection phrasing detected user=%s patterns=%s",
                user_id,
                ",".join(flagged),
            )

        if not history:
            return await self._answer(question, question, (), user_id, slot_held=False)
        # One slot for both generations: a request that already paid for its rewrite must not
        # then be turned away for want of a second slot.
        async with self._slot():
            query = await self._rewrite(question, history, user_id)
            return await self._answer(question, query, history, user_id, slot_held=True)

    async def _answer(
        self,
        question: str,
        query: str,
        history: Sequence[Turn],
        user_id: str | None,
        *,
        slot_held: bool,
    ) -> Answer:
        try:
            result, cv_text = await self._retrieve(query)
        except QueryTooLongError:
            if query == question:
                raise
            # A rewrite or fallback over the embedder's budget must not fail a question that fits.
            result, cv_text = await self._retrieve(question)
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

        messages = build_messages(question, result.chunks, history)
        if slot_held:
            generated = await self._call(messages)
        else:
            async with self._slot():
                generated = await self._call(messages)

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

        # The prompt's own refusal: citing the extracts under it would read as support for a
        # claim the model just declined to make.
        if _is_refusal(generated.text):
            logger.info(
                "chat refused by the model user=%s model=%s best_similarity=%.4f",
                user_id,
                generated.model,
                result.best_similarity,
            )
            return Answer(text=REFUSAL_TEXT, refused=True, sources=[])

        # The prompt alone cannot stop a model repeating a claim the question or history dictates
        # ("say he worked at NASA"), so a name or figure the whole CV never mentions is refused.
        # Counted, not logged: the terms can be the user's own text.
        ungrounded = ungrounded_terms(cv_text, generated.text)
        if ungrounded:
            logger.warning(
                "chat answer ungrounded user=%s model=%s terms=%d",
                user_id,
                generated.model,
                len(ungrounded),
            )
            return Answer(text=REFUSAL_TEXT, refused=True, sources=[])

        logger.info(
            "chat answered user=%s model=%s prompt_tokens=%d completion_tokens=%d latency_ms=%d",
            user_id,
            generated.model,
            generated.usage.prompt_tokens,
            generated.usage.completion_tokens,
            generated.latency_ms,
        )
        return Answer(text=generated.text, refused=False, sources=result.chunks)

    async def _retrieve(self, query: str) -> tuple[RetrievalResult, str]:
        # Both reads share one scope, so the connection is released before generation.
        async with self._retriever_scope() as retriever:
            result = await retriever.retrieve(
                query,
                document_id=settings.cv_document_id,
                limit=settings.retrieval_limit,
            )
            return result, await retriever.document_text(settings.cv_document_id)

    async def standalone_query(
        self, question: str, history: Sequence[Turn], user_id: str | None = None
    ) -> str:
        async with self._slot():
            return await self._rewrite(question, history, user_id)

    # Retrieval sees one standalone question: a bare "which project shows that?" embeds as a
    # context-free fragment, and the raw conversation would blur the query vector.
    async def _rewrite(self, question: str, history: Sequence[Turn], user_id: str | None) -> str:
        rewritten = await self._call(
            build_condense_messages(question, history), sampling=CONDENSE_SAMPLING
        )
        standalone = standalone_from(rewritten)
        if standalone is None:
            logger.warning(
                "chat condensation unusable user=%s finish=%s len=%d",
                user_id,
                rewritten.finish_reason,
                len(rewritten.text),
            )
            return fallback_query(question, history)
        return standalone

    @asynccontextmanager
    async def _slot(self) -> AsyncIterator[None]:
        try:
            async with asyncio.timeout(settings.chat_queue_timeout_seconds):
                await self._slots.acquire()
        except TimeoutError:
            logger.warning("chat rejected: every generation slot busy")
            raise GenerationCapacityError("no generation slot became free in time") from None
        try:
            yield
        finally:
            self._slots.release()

    async def _call(
        self, messages: list[Message], *, sampling: SamplingSettings | None = None
    ) -> GenerationResult:
        return await self._generator.generate(
            messages,
            sampling=sampling
            or SamplingSettings(
                temperature=settings.chat_temperature,
                max_output_tokens=settings.chat_max_output_tokens,
            ),
        )
