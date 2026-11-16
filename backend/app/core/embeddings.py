"""文本向量客户端(单一职责:把文本变成向量)。

走 OpenAI 兼容的 /embeddings 接口,因此既可以用云端服务,也可以指向自建的
开源模型服务(例如用 text-embeddings-inference / vLLM / Xinference 部署的 bge-m3),
只需改 EMBEDDING_BASE_URL / EMBEDDING_MODEL,不必把 torch 打进应用镜像。
"""

from collections.abc import Sequence
from typing import Protocol

from app.config import get_settings


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class EmbeddingNotConfigured(RuntimeError):
    """No embedding credentials: the similarity signal is skipped, not failed."""


class OpenAICompatibleEmbedder:
    def __init__(self, *, client=None, model: str | None = None):
        settings = get_settings()
        self._model = model or settings.embedding_model
        if client is None:
            if not settings.embedding_api_key:
                raise EmbeddingNotConfigured("EMBEDDING_API_KEY / DASHSCOPE_API_KEY is not set")
            from openai import OpenAI  # 延迟导入,避免测试环境强依赖

            client = OpenAI(
                api_key=settings.embedding_api_key,
                base_url=settings.embedding_base_url,
                timeout=30.0,
                max_retries=1,
            )
        self._client = client

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(model=self._model, input=list(texts))
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]
