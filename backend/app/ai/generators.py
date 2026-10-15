from app.ai.generation import ClosableGenerator
from app.ai.ollama import OllamaGenerator
from app.ai.openai import OpenAIGenerator
from app.core.config import settings


def build_generator(timeout_seconds: int) -> ClosableGenerator:
    if settings.generation_provider == "openai":
        return OpenAIGenerator(timeout_seconds=timeout_seconds)
    return OllamaGenerator(timeout_seconds=timeout_seconds)
