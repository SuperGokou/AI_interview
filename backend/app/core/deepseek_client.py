"""DeepSeek 文本推理客户端(单一职责:封装一次 system+user 的补全调用)。

DeepSeek 提供 OpenAI 兼容接口,用 openai SDK 指向其 base_url。
底层 client 可注入,便于离线测试。
"""

from typing import Optional

from app.config import get_settings


def _default_client(api_key: str, base_url: str):
    from openai import OpenAI  # 延迟导入,避免测试环境强依赖

    return OpenAI(api_key=api_key, base_url=base_url)


class DeepSeekClient:
    def __init__(self, *, model: Optional[str] = None, client=None):
        settings = get_settings()
        self._model = model or settings.deepseek_model
        self._client = client or _default_client(
            settings.deepseek_api_key, settings.deepseek_base_url
        )

    def complete(self, *, system: str, user: str, temperature: float = 0.3) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        return resp.choices[0].message.content
