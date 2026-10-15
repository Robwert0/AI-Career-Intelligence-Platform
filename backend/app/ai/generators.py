from redis.asyncio import Redis

from app.ai.generation import ClosableGenerator
from app.ai.ollama import OllamaGenerator
from app.ai.openai import OpenAIGenerator
from app.ai.spend_guard import guarded
from app.core.config import settings
from app.core.spend_ledger import SpendPool


def build_generator(timeout_seconds: int, redis: Redis, *, pool: SpendPool) -> ClosableGenerator:
    # Redis and the pool are required: no construction site can skip the guard or pick a pool late.
    provider: ClosableGenerator
    if settings.generation_provider == "openai":
        provider = OpenAIGenerator(timeout_seconds=timeout_seconds)
    else:
        provider = OllamaGenerator(timeout_seconds=timeout_seconds)
    return guarded(provider, redis, pool)
