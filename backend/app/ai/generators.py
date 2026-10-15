from redis.asyncio import Redis

from app.ai.generation import ClosableGenerator
from app.ai.ollama import OllamaGenerator
from app.ai.openai import OpenAIGenerator
from app.ai.spend_guard import guarded
from app.core.config import settings


def build_generator(timeout_seconds: int, redis: Redis) -> ClosableGenerator:
    # Redis is required here, not optional: no construction site can skip the spend guard.
    provider: ClosableGenerator
    if settings.generation_provider == "openai":
        provider = OpenAIGenerator(timeout_seconds=timeout_seconds)
    else:
        provider = OllamaGenerator(timeout_seconds=timeout_seconds)
    return guarded(provider, redis)
