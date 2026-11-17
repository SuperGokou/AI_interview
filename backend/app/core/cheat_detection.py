"""候选人回答的 AI 味检测(单一职责:用 DeepSeek 判别回答是否疑似照读 AI 稿)。

底层 DeepSeek 客户端可注入(测试传 fake),离线可测。
"""

import json
from typing import Optional

from app.core.deepseek_client import DeepSeekClient

_SYSTEM = (
    "你是面试反作弊判别官。下面是候选人【口头】回答经语音识别得到的文字,"
    "判断它是否疑似在照读 AI 生成的稿子。\n"
    "先了解这段文字的来历:语音识别会自动去掉『嗯』『啊』等语气词、补上标点、把口语整理成通顺的书面句子,"
    "所以文字通顺、有条理、用词专业、没有口头禅,都【不能】作为证据。"
    "有经验的候选人口头回答本来就会分点、有逻辑、术语准确。\n"
    "只有出现下面这类强证据时才判为疑似:\n"
    "1. 明显的书面排版痕迹被念了出来(如逐条念编号小标题、『综上所述』式的成文总结套话贯穿全篇);\n"
    "2. 面面俱到的百科式罗列,却没有任何个人经历、具体项目、数字或取舍;\n"
    "3. 内容与问题无关地过度完整,像在复述一篇现成文章;\n"
    "4. 出现 AI 口吻(如『作为一个 AI』『以下是几点建议』)。\n"
    "包含亲身经历、具体细节、自我修正、犹豫、口语化表达的回答,一律判为不疑似。"
    "拿不准时判为不疑似,并给出较低的 confidence;只有多条强证据同时出现才给 0.8 以上。\n"
    '只输出 JSON,不要多余文字:{"is_ai_like": true 或 false, "confidence": 0到1的小数, "reason": "简短理由"}'
)

# 太短的回答没有足够的信息量做判断,直接放行,避免误报。
MIN_ANSWER_CHARS = 80

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
        if len(text) < MIN_ANSWER_CHARS:
            return {"is_ai_like": False, "confidence": 0.0, "reason": "回答太短,不做判断"}
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
