"""画面与声音监考(单一职责:定期看一帧候选人画面、听一段环境声,给出需要人工复核的线索)。

模型走 OpenAI 兼容接口,可注入(测试传 fake)。两层:
- VisionProctor   问模型「这一帧(和这段声音)里有什么异常」,只接受约定的几种标记。
                  只有全模态模型(名字里带 omni)才会收到声音;其他模型只看画面。
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

# 只有真的把声音送给了模型,才接受这些标记。
AUDIO_FLAGS = (
    "keyboard_typing",  # 持续的键盘敲击声
    "other_voice",  # 候选人和面试官之外的人声
    "background_noise",  # 环境嘈杂
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

_SYSTEM_WITH_AUDIO = (
    "你是在线面试的监考助手。下面是候选人摄像头的一帧画面,以及同一时段候选人麦克风录到的几秒声音。"
    "只报告你能明确看到或听到的情况,不要猜测。可用标记(没有就给空列表):"
    "multi_person=画面中能看到第二个人(包括只露出一部分的人);"
    "person_absent=画面里没有人;"
    "gaze_off_screen=候选人明显在看屏幕以外的固定位置(侧面或下方的另一块屏幕、手机、纸张),"
    "只是眨眼、短暂低头或看镜头旁边不算;"
    "suspicious_object=能看到手机、第二块屏幕、平板、纸质资料、耳机;"
    "keyboard_typing=能清楚听到持续的键盘敲击声(连续多下),偶尔一两下点击或鼠标声不算;"
    "other_voice=能听到候选人以外的真人在说话或低声提示。面试官是 AI,它的声音可能从扬声器传进录音,"
    "那不算其他人;电视、广播等明显的背景节目声也不算,归入 background_noise;"
    "background_noise=环境明显嘈杂(多人交谈、电视、街道、施工等),会影响面试。"
    "detail 用一句中文描述你看到和听到的依据,并顺带说明候选人神态和背景环境。"
    '只输出 JSON:{"flags":["..."],"detail":"..."}'
)


class VisionClient(Protocol):
    # 支持声音的客户端另有 accepts_audio 属性,并接受 wav / note 两个关键字参数。
    def describe(self, *, system: str, jpeg: bytes) -> str: ...


def _hears(model: str) -> bool:
    return "omni" in model.lower()


class ProctorUnavailable(RuntimeError):
    """None of the configured vision models can be used; stop trying for this interview."""


def _is_missing_model(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    return status == 404 or "model_not_found" in str(exc) or "Model not exist" in str(exc)


class OpenAICompatibleVision:
    def __init__(self, *, client=None, model: str | None = None):
        settings = get_settings()
        # Several names may be given, best first: model catalogues differ between
        # accounts and regions, and a name that works for one key 404s for another.
        names = model or settings.proctor_model
        self._models = [name.strip() for name in names.split(",") if name.strip()]
        if client is None:
            from openai import OpenAI  # 延迟导入,避免测试环境强依赖

            client = OpenAI(
                api_key=settings.proctor_api_key,
                base_url=settings.proctor_base_url,
                timeout=20.0,
                max_retries=0,
            )
        self._client = client

    @property
    def accepts_audio(self) -> bool:
        """Whether the model that will answer next can listen as well as look."""
        return bool(self._models) and _hears(self._models[0])

    def describe(
        self, *, system: str, jpeg: bytes, wav: bytes | None = None, note: str = ""
    ) -> str:
        image = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
        while self._models:
            model = self._models[0]
            content: list[dict] = [{"type": "image_url", "image_url": {"url": image}}]
            if wav and _hears(model):
                audio = "data:;base64," + base64.b64encode(wav).decode()
                content.append(
                    {"type": "input_audio", "input_audio": {"data": audio, "format": "wav"}}
                )
                request = "请检查这一帧画面和这段声音。"
            else:
                request = "请检查这一帧画面。"
            content.append({"type": "text", "text": f"{request}{note}"})
            try:
                # Streamed: the omni models only answer in streaming mode.
                stream = self._client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": content},
                    ],
                    temperature=0.0,
                    max_tokens=300,
                    stream=True,
                    # A yes/no look at one frame does not need deep reasoning.
                    extra_body={"enable_thinking": False},
                )
                return _collect(stream)
            except Exception as exc:
                if not _is_missing_model(exc):
                    raise
                logger.warning("proctoring model %s is not available for this key", model)
                self._models = self._models[1:]
        raise ProctorUnavailable("no configured vision model is available (set PROCTOR_MODEL)")


def _collect(stream) -> str:
    """Join the text of a streamed chat completion."""
    parts: list[str] = []
    for chunk in stream:
        choices = getattr(chunk, "choices", None)
        if not choices:
            continue  # the closing usage chunk has no choices
        text = getattr(choices[0].delta, "content", None)
        if text:
            parts.append(text)
    return "".join(parts)


class VisionProctor:
    def __init__(self, client: VisionClient | None = None):
        self._client = client or OpenAICompatibleVision()

    def check(self, jpeg: bytes, wav: bytes | None = None, *, note: str = "") -> dict:
        """Returns {"flags": [...], "detail": str}; unknown flags are dropped.

        wav: a few seconds of the candidate's surroundings. It is only used, and
        sound flags are only accepted, when the model can actually listen.
        """
        heard = bool(wav) and getattr(self._client, "accepts_audio", False)
        if heard:
            raw = self._client.describe(
                system=_SYSTEM_WITH_AUDIO, jpeg=jpeg, wav=wav, note=note
            )
            allowed = ALLOWED_FLAGS + AUDIO_FLAGS
        else:
            raw = self._client.describe(system=_SYSTEM, jpeg=jpeg)
            allowed = ALLOWED_FLAGS
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
            "flags": [f for f in flags if f in allowed] if isinstance(flags, list) else [],
            "detail": detail.strip()[:300] if isinstance(detail, str) else "",
        }


# Things that are either in the picture or not: one clear sighting is enough, and
# they can be brief (a phone held up for a few seconds). Gaze and absence are
# judgement calls on a single frame, so those need two checks in a row.
# A second voice can also be brief (a whispered hint), so it counts at once;
# typing and noise have to persist across two checks.
IMMEDIATE_FLAGS = frozenset({"multi_person", "suspicious_object", "other_voice"})


class ProctorMonitor:
    """Debounce: objects and extra people count at once, gaze and absence need two
    consecutive checks; a reported flag is not repeated for a while."""

    def __init__(self, *, cooldown_s: float = 120.0):
        self._cooldown_s = cooldown_s
        self._previous: frozenset[str] = frozenset()
        self._reported_at: dict[str, float] = {}

    def update(self, flags: list[str], now: float) -> list[str]:
        current = frozenset(flags)
        confirmed = [
            flag
            for flag in sorted(current)
            if (flag in IMMEDIATE_FLAGS or flag in self._previous)
            and now - self._reported_at.get(flag, float("-inf")) >= self._cooldown_s
        ]
        self._reported_at = {**self._reported_at, **{flag: now for flag in confirmed}}
        self._previous = current
        return confirmed
