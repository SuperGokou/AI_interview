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


def test_monitor_needs_two_consecutive_sightings_then_cools_down():
    monitor = ProctorMonitor(cooldown_s=120)
    assert monitor.update(["multi_person"], 0) == []  # one frame could be a mistake
    assert monitor.update(["multi_person"], 20) == ["multi_person"]
    assert monitor.update(["multi_person"], 40) == []  # same problem, no repeat yet
    assert monitor.update(["multi_person", "suspicious_object"], 150) == ["multi_person"]
    assert monitor.update(["suspicious_object"], 170) == ["suspicious_object"]


def test_monitor_forgets_a_flag_that_did_not_repeat():
    monitor = ProctorMonitor()
    monitor.update(["gaze_off_screen"], 0)
    assert monitor.update([], 20) == []
    assert monitor.update(["gaze_off_screen"], 40) == []  # not consecutive


class _Bridge:
    def __init__(self, **_kwargs): pass
    async def connect(self): pass
    async def events(self): await asyncio.Event().wait()
    async def trigger_response(self, instructions=""): pass
    async def send_audio(self, pcm): pass
    async def send_image(self, jpeg): pass
    async def close(self): pass


def test_websocket_records_a_confirmed_camera_finding(client, db_session, monkeypatch):
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
        import time
        time.sleep(0.15)
        ws.send_text(frame(b"frame-2"))  # the second sighting confirms it
        assert ws.receive_json() == {"type": "integrity", "level": "red"}

    db_session.expire_all()
    events = db_session.query(models.CheatEvent).all()
    assert [(e.kind, e.severity) for e in events] == [("multi_person", "high")]
    assert "第二个人" in events[0].evidence
    assert vision.frames[:2] == [b"frame-1", b"frame-2"]  # an unchanged frame is not re-checked
