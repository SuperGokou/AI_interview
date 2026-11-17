from app.core.cheat_detection import AiTextDetector


class _FakeDeepSeek:
    def __init__(self, response):
        self._r = response
        self.calls = []

    def complete(self, *, system, user, temperature):
        self.calls.append((system, user, temperature))
        return self._r


def test_detect_parses_ai_like_true():
    det = AiTextDetector(client=_FakeDeepSeek(
        '{"is_ai_like": true, "confidence": 0.9, "reason": "教科书腔"}'
    ))
    out = det.detect("这是一段非常结构化、面面俱到的回答。" * 6)
    assert out["is_ai_like"] is True
    assert out["confidence"] == 0.9
    assert "教科书" in out["reason"]


def test_detect_handles_code_fence():
    det = AiTextDetector(client=_FakeDeepSeek(
        '```json\n{"is_ai_like": false, "confidence": 0.1, "reason": "口语自然"}\n```'
    ))
    out = det.detect("嗯……我觉得吧,大概是这样。" * 8)
    assert out["is_ai_like"] is False


def test_detect_empty_answer_short_circuits_without_calling_model():
    fake = _FakeDeepSeek("should not be called")
    det = AiTextDetector(client=fake)
    out = det.detect("   ")
    assert out["is_ai_like"] is False
    assert fake.calls == []


def test_detect_unparseable_output_is_safe():
    det = AiTextDetector(client=_FakeDeepSeek("这不是 JSON"))
    out = det.detect("一段回答" * 30)
    assert out["is_ai_like"] is False
    assert "无法解析" in out["reason"]


def test_short_answer_is_not_judged():
    fake = _FakeDeepSeek('{"is_ai_like": true, "confidence": 0.99, "reason": "x"}')
    out = AiTextDetector(client=fake).detect("我之前主要做推荐系统的排序模型。")
    assert out["is_ai_like"] is False
    assert fake.calls == []


def test_prompt_tells_the_judge_the_text_is_a_speech_transcript():
    fake = _FakeDeepSeek('{"is_ai_like": false, "confidence": 0.1, "reason": "自然"}')
    AiTextDetector(client=fake).detect("我" * 120)
    system = fake.calls[0][0]
    assert "语音识别" in system
    assert "拿不准时判为不疑似" in system


def test_ai_text_hit_is_a_weak_signal_unless_very_confident():
    from app.api.interview_ws import _AI_TEXT_THRESHOLD, _ai_text_severity

    assert _AI_TEXT_THRESHOLD >= 0.8
    assert _ai_text_severity(0.85) == "low"
    assert _ai_text_severity(0.95) == "medium"
