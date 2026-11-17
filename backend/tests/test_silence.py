"""Breaking a long silence: check in, move on, then stop and wait."""

import asyncio
import base64
import json

from app.core.silence import CHECK_IN, MOVE_ON, PAUSE, SilenceWatch, nudge_text
from app.db import models


def test_nothing_happens_before_the_interviewer_has_spoken():
    assert SilenceWatch().due(1000) is None


def test_checks_in_then_moves_on_counting_from_the_end_of_playback():
    watch = SilenceWatch(check_in_s=20, move_on_s=25)
    watch.interviewer_audio(10, now=0)  # generated at once, plays until t=10
    assert watch.due(29) is None
    assert watch.due(30) == CHECK_IN
    assert watch.due(31) is None  # fires once
    watch.interviewer_audio(4, now=31)  # the check-in itself plays until t=35
    assert watch.due(59) is None
    assert watch.due(60) == MOVE_ON


def test_candidate_speaking_resets_the_wait():
    watch = SilenceWatch(check_in_s=20, move_on_s=25)
    watch.interviewer_audio(5, now=0)
    watch.candidate_active(now=20)  # started answering just in time
    assert watch.due(39) is None
    assert watch.due(40) == CHECK_IN
    watch.candidate_active(now=41)
    assert watch.due(60) is None  # the check-in was answered, so no move-on


def test_stops_asking_after_several_unanswered_questions_until_the_candidate_returns():
    watch = SilenceWatch(check_in_s=10, move_on_s=10, max_skipped=2)
    watch.interviewer_audio(0, now=0)
    stages = [watch.due(t) for t in range(0, 200, 10)]
    assert [s for s in stages if s] == [CHECK_IN, MOVE_ON, CHECK_IN, PAUSE]
    watch.candidate_active(now=300)
    assert watch.due(310) == CHECK_IN


def test_nudges_never_offer_the_answer():
    for language in ("zh", "en"):
        for stage in (CHECK_IN, MOVE_ON, PAUSE):
            assert nudge_text(stage, language)
    assert "不要给提示" in nudge_text(CHECK_IN)


def test_a_repeated_silence_is_not_met_with_the_same_sentence():
    assert nudge_text(CHECK_IN) != nudge_text(CHECK_IN, repeated=True)
    assert "不要重复" in nudge_text(MOVE_ON, repeated=True)
    watch = SilenceWatch(check_in_s=10, move_on_s=10)
    watch.interviewer_audio(0, now=0)
    assert not watch.repeated
    assert [watch.due(10), watch.due(20)] == [CHECK_IN, MOVE_ON]
    assert watch.repeated  # the next check-in is for a second unanswered question


def test_knows_whether_the_interviewer_is_still_audible():
    watch = SilenceWatch()
    assert not watch.interviewer_speaking(0)
    watch.interviewer_audio(10, now=0)
    assert watch.interviewer_speaking(9)
    assert not watch.interviewer_speaking(10.5)
    assert watch.interviewer_speaking(10.5, margin=1)  # the page plays a little late
    watch.cut_short(now=4)
    assert not watch.interviewer_speaking(4.1)


class _Bridge:
    prompts: list[str] = []

    def __init__(self, **_kwargs):
        self._events = asyncio.Queue()
        self._events.put_nowait({"kind": "audio", "data": bytes(4800)})  # 0.1 s of speech

    async def connect(self): pass
    async def events(self): return await self._events.get()
    async def trigger_response(self, instructions=""): _Bridge.prompts.append(instructions)
    async def send_audio(self, pcm): pass
    async def send_image(self, jpeg): pass
    async def close(self): pass


def test_websocket_prompts_the_interviewer_when_the_candidate_stays_silent(
    client, db_session, monkeypatch
):
    job = models.Job(title="后端", jd="x", interviewer_voice="Tina")
    cand = models.Candidate(name="王五")
    db_session.add_all([job, cand])
    db_session.commit()
    db_session.add(models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token="tok-quiet"))
    db_session.commit()

    _Bridge.prompts = []
    monkeypatch.setattr("app.api.interview_ws.bridge_factory", _Bridge)
    monkeypatch.setattr("app.api.interview_ws.ai_detector_factory", lambda: object())
    monkeypatch.setattr(
        "app.api.interview_ws.SilenceWatch", lambda **_kw: SilenceWatch(check_in_s=0.05, move_on_s=60)
    )
    real_sleep = asyncio.sleep

    async def fast_sleep(seconds):
        await real_sleep(0.05 if seconds >= 1 else seconds)

    monkeypatch.setattr("app.api.interview_ws.asyncio.sleep", fast_sleep)

    with client.websocket_connect("/ws/interview?token=tok-quiet") as ws:
        assert ws.receive_json()["type"] == "audio"
        frame = json.dumps({"type": "image", "data": base64.b64encode(b"f").decode()})
        for _ in range(40):
            if any("没有说话" in p for p in _Bridge.prompts):
                break
            ws.send_text(frame)
            import time; time.sleep(0.02)

    assert any("没有说话" in p for p in _Bridge.prompts)
