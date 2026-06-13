"""候选人回答的 AI 味检测(单一职责:用 DeepSeek 判别回答是否疑似照读 AI 稿)。

底层 DeepSeek 客户端可注入(测试传 fake),离线可测。
"""

import json
from typing import Optional

from app.core.deepseek_client import DeepSeekClient

_SYSTEM = (
    "你是面试反作弊判别官。判断候选人这段【口头】回答是否疑似在照读 AI 生成的稿子"
    "(过度结构化、教科书腔、信息密度异常、与自然口语不符)。"
    '只输出 JSON,不要多余文字:{"is_ai_like": true 或 false, "confidence": 0到1的小数, "reason": "简短理由"}'
)

_SAFE_DEFAULT = {"is_ai_like": False, "confidence": 0.0, "reason": "无法解析判别结果"}


def _extract_json(raw: str) -> str:
    """从可能带 ```json fence 或多余文字的输出里抠出 JSON 对象。"""
    s = (raw or "").strip()
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return s[start : end + 1]
    return s


class AiTextDetector:
    def __init__(self, client: Optional[object] = None):
        # client 仅需提供 complete(*, system, user, temperature) -> str
        self._client = client or DeepSeekClient()

    def detect(self, answer: str) -> dict:
        text = (answer or "").strip()
        if not text:
            return {"is_ai_like": False, "confidence": 0.0, "reason": "空回答"}
        raw = self._client.complete(system=_SYSTEM, user=text, temperature=0.0)
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> dict:
        try:
            data = json.loads(_extract_json(raw))
            return {
                "is_ai_like": bool(data.get("is_ai_like", False)),
                "confidence": float(data.get("confidence", 0.0)),
                "reason": str(data.get("reason", "")),
            }
        except Exception:
            return dict(_SAFE_DEFAULT)
