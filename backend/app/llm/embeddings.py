"""
文本向量化：OpenAI 兼容的 embeddings 接口，默认硅基流动的 BAAI/bge-m3。

没有配置 Key 时 enabled() 返回 False，检索自动退化为只用关键词，其他功能不受影响。
"""
import time
from functools import lru_cache

import openai

from app.core.config import settings
from app.llm.callbacks import record_call

BATCH_SIZE = 32


def enabled() -> bool:
    return bool(settings.embedding_api_key)


@lru_cache
def _client() -> openai.OpenAI:
    return openai.OpenAI(
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
        timeout=settings.embedding_timeout,
        max_retries=2,
    )


def embed(texts: list[str]) -> list[list[float]]:
    """批量向量化，返回顺序与输入一致。失败时抛出 openai 的异常，由调用方决定怎么降级。"""
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        start = time.perf_counter()
        try:
            resp = _client().embeddings.create(model=settings.embedding_model, input=batch)
        except Exception as e:
            record_call("embedding", settings.embedding_model, _ms(start), ok=False, error=f"{type(e).__name__}: {e}")
            raise
        usage = getattr(resp, "usage", None)
        record_call("embedding", settings.embedding_model, _ms(start), ok=True,
                    input_tokens=getattr(usage, "prompt_tokens", None))
        vectors.extend(d.embedding for d in sorted(resp.data, key=lambda d: d.index))
    return vectors


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)
