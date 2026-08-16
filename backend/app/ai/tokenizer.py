from functools import lru_cache

from transformers import AutoTokenizer, PreTrainedTokenizerBase

from app.core.config import settings

# [CLS] and [SEP] are prepended/appended by the encoder and count against the model limit,
# so usable content is always two tokens short of it.
SPECIAL_TOKEN_ALLOWANCE = 2


@lru_cache(maxsize=1)
def get_tokenizer() -> PreTrainedTokenizerBase:
    return AutoTokenizer.from_pretrained(settings.embedding_model)


def count_tokens(text: str) -> int:
    return len(get_tokenizer().encode(text, add_special_tokens=False))


def token_budget() -> int:
    return int(get_tokenizer().model_max_length) - SPECIAL_TOKEN_ALLOWANCE
