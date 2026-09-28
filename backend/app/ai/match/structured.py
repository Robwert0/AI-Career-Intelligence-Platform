from dataclasses import replace
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.generation import (
    ContextOverflowError,
    GenerationRequestError,
    GenerationResult,
    Generator,
    GeneratorUnavailableError,
    Message,
    Role,
    SamplingSettings,
)
from app.ai.match.prompts import correction_message
from app.ai.output_guard import Verdict, validate_output

_LEAK_CHECKS = frozenset({"canary", "ngram"})


class ExtractionError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def _generate(
    generator: Generator,
    messages: list[Message],
    sampling: SamplingSettings,
    schema: dict[str, Any],
) -> GenerationResult:
    try:
        return await generator.generate(messages, sampling=sampling, response_schema=schema)
    except GeneratorUnavailableError:
        raise ExtractionError("ai_unavailable") from None
    except ContextOverflowError:
        raise ExtractionError("input_too_long") from None
    except GenerationRequestError:
        raise ExtractionError("internal_error") from None


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def _checked(result: GenerationResult, system_prompt: str) -> Verdict:
    verdict = validate_output(result, protected_prompt=system_prompt)
    if verdict.failed_check in _LEAK_CHECKS:
        raise ExtractionError("ai_invalid_output")
    return verdict


def _parse[T: BaseModel](
    result: GenerationResult, model: type[T], system_prompt: str
) -> tuple[T | None, str]:
    verdict = _checked(result, system_prompt)
    if not verdict.ok:
        return None, f"reply was {verdict.failed_check}"
    try:
        parsed = model.model_validate_json(result.text)
    except ValidationError as exc:
        # Paths and error types only: echoing the reply back would feed its content forward.
        problems = (
            f"{'.'.join(str(part) for part in error['loc']) or 'reply'}: {error['type']}"
            for error in exc.errors()[:10]
        )
        return None, "; ".join(problems)
    # The raw check sees JSON source; \u escapes and item boundaries hide what the user reads.
    _checked(replace(result, text="\n".join(_strings(parsed.model_dump()))), system_prompt)
    return parsed, ""


async def generate_validated[T: BaseModel](
    generator: Generator,
    messages: list[Message],
    model: type[T],
    sampling: SamplingSettings,
) -> T:
    """One schema-constrained call, one corrective retry, then ai_invalid_output."""
    # The system prompt is what a leak would expose, so it is what the n-gram check protects.
    system_prompt = next((m.content for m in messages if m.role is Role.SYSTEM), None)
    if system_prompt is None:
        raise ValueError("a structured call needs a system prompt")
    schema = model.model_json_schema()
    first = await _generate(generator, messages, sampling, schema)
    parsed, problems = _parse(first, model, system_prompt)
    if parsed is None:
        retry = [*messages, correction_message(problems)]
        second = await _generate(generator, retry, sampling, schema)
        parsed, _ = _parse(second, model, system_prompt)
    if parsed is None:
        raise ExtractionError("ai_invalid_output")
    return parsed
