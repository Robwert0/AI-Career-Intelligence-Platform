import functools

from transformers import AutoTokenizer, PreTrainedTokenizerBase

from app.core.config import settings


@functools.lru_cache
def get_tokenizer() -> PreTrainedTokenizerBase:
    return AutoTokenizer.from_pretrained(
        settings.embedding_model, revision=settings.embedding_model_revision
    )


def count_tokens(text: str) -> int:
    tokenizer = get_tokenizer()
    return len(tokenizer.encode(text, add_special_tokens=False))


def token_budget() -> int:
    tokenizer = get_tokenizer()
    model_length = tokenizer.model_max_length - 2
    return model_length
