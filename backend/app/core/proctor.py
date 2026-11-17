"""画面监考(单一职责:定期看一帧候选人画面,给出需要人工复核的线索)。

视觉模型走 OpenAI 兼容接口,可注入(测试传 fake)。两层:
- VisionProctor   问模型「这一帧里有什么异常」,只接受约定的几种标记。
- ProctorMonitor  去抖:同一标记连续两次出现才记一条,之后冷却一段时间,
                  避免单帧误判和同一问题刷屏。纯逻辑。
这些都是线索,不是结论:光线、摄像头角度、候选人低头思考都可能触发。
"""

import base64
import json
import logging
from typing import Protocol

from app.config import get_settings

logger = logging.getLogger(__name__)

ALLOWED_FLAGS = (
    "multi_person",  # 画面里不止一个人
    "person_absent",  # 候选人不在画面里
    "gaze_off_screen",  # 明显长时间看向屏幕外
    "suspicious_object",  # 手机、第二块屏幕、纸质资料、耳机等
)

_SYSTEM = (
    "你是在线面试的监考助手。下面是候选人摄像头的一帧画面。只报告你能明确看到的情况,不要猜测。"
    "可用标记(没有就给空列表):"
    "multi_person=画面中能看到第二个人(包括只露出一部分的人);"
    "person_absent=画面里没有人;"
    "gaze_off_screen=候选人明显在看屏幕以外的固定位置(侧面或下方的另一块屏幕、手机、纸张),"
    "只是眨眼、短暂低头或看镜头旁边不算;"
    "suspicious_object=能看到手机、第二块屏幕、平板、纸质资料、耳机。"
    "detail 用一句中文描述你看到的依据,并顺带说明候选人神态(如专注、紧张、频繁看别处)和背景环境"
    "(如办公室、卧室、公共场所、有他人走动)。"
    '只输出 JSON:{"flags":["..."],"detail":"..."}'
)


class VisionClient(Protocol):
    def describe(self, *, system: str, jpeg: bytes) -> str: ...


class OpenAICompatibleVision:
    def __init__(self, *, client=None, model: str | None = None):
        settings = get_settings()
        self._model = model or settings.proctor_model
        if client is None:
            from openai import OpenAI  # 延迟导入,避免测试环境强依赖

            client = OpenAI(
                api_key=settings.proctor_api_key,
                base_url=settings.proctor_base_url,
                timeout=20.0,
                max_retries=0,
            )
        self._client = client

    def describe(self, *, system: str, jpeg: bytes) -> str:
        image = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": [{"type": "image_url", "image_url": {"url": image}}]},
            ],
            temperature=0.0,
            max_tokens=300,
        )
        return response.choices[0].message.content or ""


class VisionProctor:
    def __init__(self, client: VisionClient | None = None):
        self._client = client or OpenAICompatibleVision()

    def check(self, jpeg: bytes) -> dict:
        """Returns {"flags": [...], "detail": str}; unknown flags are dropped."""
        raw = self._client.describe(system=_SYSTEM, jpeg=jpeg)
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end <= start:
            return {"flags": [], "detail": ""}
        try:
            data = json.loads(raw[start : end + 1])
        except ValueError:
            return {"flags": [], "detail": ""}
        flags = data.get("flags") if isinstance(data, dict) else None
        detail = data.get("detail") if isinstance(data, dict) else ""
        return {
            "flags": [f for f in flags if f in ALLOWED_FLAGS] if isinstance(flags, list) else [],
            "detail": detail.strip()[:300] if isinstance(detail, str) else "",
        }


class ProctorMonitor:
    """A flag is reported when two consecutive checks agree, then not again for a while."""

    def __init__(self, *, cooldown_s: float = 120.0):
        self._cooldown_s = cooldown_s
        self._previous: frozenset[str] = frozenset()
        self._reported_at: dict[str, float] = {}

    def update(self, flags: list[str], now: float) -> list[str]:
        current = frozenset(flags)
        confirmed = [
            flag
            for flag in sorted(current & self._previous)
            if now - self._reported_at.get(flag, float("-inf")) >= self._cooldown_s
        ]
        self._reported_at = {**self._reported_at, **{flag: now for flag in confirmed}}
        self._previous = current
        return confirmed
