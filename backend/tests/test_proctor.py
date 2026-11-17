"""Camera proctoring: model output parsing, debouncing, and websocket wiring."""

import asyncio
import base64
import json

from app.core.proctor import ProctorMonitor, VisionProctor
from app.db import models


class _Vision:
    def __init__(self, reply):
        self.reply, self.frames = reply, []

    def describe(self, *, system, jpeg):
        self.frames.append(jpeg)
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


def test_proctor_keeps_only_known_flags():
    proctor = VisionProctor(_Vision({"flags": ["multi_person", "is_cheating", 7], "detail": " 身后有第二个人 "}))
    assert proctor.check(b"jpeg") == {"flags": ["multi_person"], "detail": "身后有第二个人"}


def test_proctor_tolerates_fenced_or_malformed_output():
    fenced = '```json\n{"flags": ["person_absent"], "detail": "无人"}\n```'
    assert VisionProctor(_Vision(fenced)).check(b"x")["flags"] == ["person_absent"]
    for junk in ("我无法判断", "{not json}", '{"flags": "multi_person"}', "[]"):
        assert VisionProctor(_Vision(junk)).check(b"x")["flags"] == []


def test_objects_and_extra_people_count_on_first_sight_then_cool_down():
    monitor = ProctorMonitor(cooldown_s=120)
    assert monitor.update(["suspicious_object"], 0) == ["suspicious_object"]  # a phone held up briefly
    assert monitor.update(["suspicious_object", "multi_person"], 8) == ["multi_person"]
    assert monitor.update(["suspicious_object"], 60) == []  # same problem, no repeat yet
    assert monitor.update(["phone"], 62) == ["phone"]  # a phone is its own finding
    assert monitor.update(["suspicious_object"], 130) == ["suspicious_object"]


def test_gaze_and_absence_need_two_consecutive_checks():
    monitor = ProctorMonitor()
    assert monitor.update(["gaze_off_screen"], 0) == []  # one frame could be a glance
    assert monitor.update([], 8) == []
    assert monitor.update(["gaze_off_screen"], 16) == []  # not consecutive
    assert monitor.update(["gaze_off_screen", "person_absent"], 24) == ["gaze_off_screen"]
    assert monitor.update(["person_absent"], 32) == ["person_absent"]


def test_vision_client_falls_back_to_the_next_model_and_gives_up_cleanly():
    import pytest

    from app.core.proctor import OpenAICompatibleVision, ProctorUnavailable

    class _Missing(Exception):
        status_code = 404

    calls = []

    class _Completions:
        def create(self, *, model, **_kwargs):
            calls.append(model)
            if model != "works":
                raise _Missing("Model not exist.")
            return _stream('{"flags": [], ', '"detail": "ok"}')

    client = type("Client", (), {"chat": type("Chat", (), {"completions": _Completions()})()})()
    vision = OpenAICompatibleVision(client=client, model="gone-1, gone-2, works")
    assert "ok" in vision.describe(system="s", jpeg=b"x")
    assert "ok" in vision.describe(system="s", jpeg=b"x")
    assert calls == ["gone-1", "gone-2", "works", "works"]  # dead names are not retried

    none_left = OpenAICompatibleVision(client=client, model="gone-1")
    with pytest.raises(ProctorUnavailable):
        none_left.describe(system="s", jpeg=b"x")


def _stream(*pieces):
    """A streamed chat completion: one chunk per piece, then a usage-only chunk."""
    chunks = [
        type("Chunk", (), {"choices": [type("C", (), {"delta": type("D", (), {"content": p})()})()]})()
        for p in pieces
    ]
    return [*chunks, type("Chunk", (), {"choices": []})()]


class _Recorder:
    """Stands in for the OpenAI client and keeps every request."""

    def __init__(self, missing=()):
        self.requests, self._missing = [], set(missing)
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if kwargs["model"] in self._missing:
            raise type("Missing", (Exception,), {"status_code": 404})("Model not exist.")
        return _stream('{"flags": ["keyboard_typing", "multi_person"], "detail": "有键盘声"}')


def _parts(request):
    return [part["type"] for part in request["messages"][1]["content"]]


def test_omni_model_gets_the_sound_and_may_report_sound_flags():
    from app.core.proctor import OpenAICompatibleVision

    client = _Recorder()
    proctor = VisionProctor(OpenAICompatibleVision(client=client, model="qwen3.8-omni-flash, plain-vl"))
    result = proctor.check(b"jpeg", b"RIFFwav", note="面试官正在说话")
    assert result["flags"] == ["keyboard_typing", "multi_person"]
    request = client.requests[0]
    assert _parts(request) == ["image_url", "input_audio", "text"]
    assert request["stream"] is True
    assert "键盘" in request["messages"][0]["content"]
    assert "面试官正在说话" in request["messages"][1]["content"][-1]["text"]


def test_picture_only_model_never_gets_sound_and_sound_flags_are_dropped():
    from app.core.proctor import OpenAICompatibleVision

    client = _Recorder()
    proctor = VisionProctor(OpenAICompatibleVision(client=client, model="plain-vl"))
    assert proctor.check(b"jpeg", b"RIFFwav")["flags"] == ["multi_person"]
    assert _parts(client.requests[0]) == ["image_url", "text"]
    assert "键盘" not in client.requests[0]["messages"][0]["content"]


def test_falling_back_from_the_omni_model_drops_the_sound_mid_request():
    from app.core.proctor import OpenAICompatibleVision

    client = _Recorder(missing={"qwen3.8-omni-flash"})
    vision = OpenAICompatibleVision(client=client, model="qwen3.8-omni-flash, plain-vl")
    proctor = VisionProctor(vision)
    proctor.check(b"jpeg", b"RIFFwav")
    assert [_parts(r) for r in client.requests] == [
        ["image_url", "input_audio", "text"],
        ["image_url", "text"],
    ]
    assert vision.accepts_audio is False
    # From now on the model cannot hear, so what it says about sound is ignored.
    assert proctor.check(b"jpeg", b"RIFFwav")["flags"] == ["multi_person"]


def test_a_second_voice_counts_at_once_typing_needs_two_checks():
    monitor = ProctorMonitor()
    assert monitor.update(["other_voice", "keyboard_typing"], 0) == ["other_voice"]
    assert monitor.update(["keyboard_typing"], 8) == ["keyboard_typing"]


def test_audio_window_keeps_recent_sound_and_skips_silence():
    import struct
    import wave
    from io import BytesIO

    from app.core.proctor_audio import AudioWindow, pcm_to_wav, worth_hearing

    loud = struct.pack("<8000h", *([4000, -4000] * 4000))  # 0.5 s
    window = AudioWindow(max_seconds=2)
    for _ in range(10):  # 5 s in, only the last 2 s kept
        window.append(loud)
    pcm = window.take()
    assert len(pcm) == 2 * 16000 * 2
    assert window.take() == b""
    assert worth_hearing(pcm)
    assert not worth_hearing(bytes(len(pcm)))  # silence
    assert not worth_hearing(loud)  # too short
    with wave.open(BytesIO(pcm_to_wav(pcm))) as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getnframes()) == (16000, 1, 32000)


class _Hearing:
    accepts_audio = True

    def __init__(self):
        self.calls = []

    def describe(self, *, system, jpeg, wav=None, note=""):
        self.calls.append((wav, note))
        return json.dumps({"flags": ["other_voice"], "detail": "有人在旁边小声提示"})


def test_websocket_sends_room_sound_to_the_proctor(client, db_session, monkeypatch):
    import struct

    job = models.Job(title="后端", jd="x", interviewer_voice="Tina")
    cand = models.Candidate(name="李四")
    db_session.add_all([job, cand])
    db_session.commit()
    db_session.add(models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token="tok-sound"))
    db_session.commit()

    hearing = _Hearing()
    monkeypatch.setattr("app.api.interview_ws.bridge_factory", _Bridge)
    monkeypatch.setattr("app.api.interview_ws.ai_detector_factory", lambda: object())
    monkeypatch.setattr("app.api.interview_ws.proctor_factory", lambda: VisionProctor(hearing))

    real_sleep = asyncio.sleep

    async def fast_sleep(seconds):
        await real_sleep(0.2 if seconds >= 1 else seconds)

    monkeypatch.setattr("app.api.interview_ws.asyncio.sleep", fast_sleep)

    second = struct.pack("<16000h", *([3000, -3000] * 8000))

    def message(kind, payload):
        return json.dumps({"type": kind, "data": base64.b64encode(payload).decode()})

    with client.websocket_connect("/ws/interview?token=tok-sound") as ws:
        for _ in range(3):
            ws.send_text(message("proctor_audio", second))
        ws.send_text(message("image", b"frame-1"))
        assert ws.receive_json() == {"type": "integrity", "level": "yellow"}

    db_session.expire_all()
    events = db_session.query(models.CheatEvent).all()
    assert [(e.kind, e.severity) for e in events] == [("other_voice", "medium")]
    wav, _note = hearing.calls[0]
    assert wav[:4] == b"RIFF" and len(wav) > 3 * 32000


class _Bridge:
    def __init__(self, **_kwargs): pass
    async def connect(self): pass
    async def events(self): await asyncio.Event().wait()
    async def trigger_response(self, instructions=""): pass
    async def send_audio(self, pcm): pass
    async def send_image(self, jpeg): pass
    async def close(self): pass


def test_websocket_records_a_camera_finding(client, db_session, monkeypatch):
    job = models.Job(title="后端", jd="x", interviewer_voice="Tina")
    cand = models.Candidate(name="张三")
    db_session.add_all([job, cand])
    db_session.commit()
    db_session.add(models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token="tok-proctor"))
    db_session.commit()

    vision = _Vision({"flags": ["multi_person"], "detail": "画面右侧有第二个人"})
    monkeypatch.setattr("app.api.interview_ws.bridge_factory", _Bridge)
    monkeypatch.setattr("app.api.interview_ws.ai_detector_factory", lambda: object())
    monkeypatch.setattr("app.api.interview_ws.proctor_factory", lambda: VisionProctor(vision))

    real_sleep = asyncio.sleep

    async def fast_sleep(seconds):
        await real_sleep(0.03 if seconds >= 1 else seconds)

    monkeypatch.setattr("app.api.interview_ws.asyncio.sleep", fast_sleep)

    def frame(tag):
        return json.dumps({"type": "image", "data": base64.b64encode(tag).decode()})

    with client.websocket_connect("/ws/interview?token=tok-proctor") as ws:
        ws.send_text(frame(b"frame-1"))
        assert ws.receive_json() == {"type": "integrity", "level": "red"}

    db_session.expire_all()
    events = db_session.query(models.CheatEvent).all()
    assert [(e.kind, e.severity) for e in events] == [("multi_person", "high")]
    assert "第二个人" in events[0].evidence
    assert vision.frames == [b"frame-1"]  # an unchanged frame is not re-checked


def test_a_phone_is_reported_even_right_after_another_object():
    """Seen in a real interview: a monitor in the background was reported first and
    the cooldown then hid the phone the candidate held up half a minute later."""
    monitor = ProctorMonitor()
    assert monitor.update(["suspicious_object"], 0) == ["suspicious_object"]
    assert monitor.update(["phone", "suspicious_object"], 35) == ["phone"]
    proctor = VisionProctor(_Vision({"flags": ["phone"], "detail": "手里拿着手机"}))
    assert proctor.check(b"x")["flags"] == ["phone"]
