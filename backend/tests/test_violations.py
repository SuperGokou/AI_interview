"""Typing during a spoken interview: warned on the spot, ended when it keeps happening."""

import asyncio
import base64
import json
import struct

from app.core.proctor import VisionProctor
from app.core.violations import END, WARN, ViolationPolicy, ending_text, warning_text
from app.db import models


def test_two_warnings_then_the_third_violation_ends_the_interview():
    policy = ViolationPolicy(limit=3)
    actions = [policy.record(kinds) for kinds in (["keyboard_typing"], ["phone"], ["other_voice"])]
    assert actions == [WARN, WARN, END]


def test_judgement_calls_are_not_violations_and_zero_switches_it_off():
    policy = ViolationPolicy(limit=3)
    assert policy.record(["gaze_off_screen", "suspicious_object", "background_noise"]) is None
    assert policy.count == 0
    assert policy.record(["phone", "multi_person"]) == WARN  # one check, one violation
    assert policy.count == 1
    assert ViolationPolicy(limit=0).record(["keyboard_typing"]) is None


def test_wording_says_what_was_noticed_and_how_many_are_left():
    first = warning_text(["phone"], 1, 3)
    assert "手机" in first and "第 1 次违规" in first and "最后一次提醒" not in first
    second = warning_text(["keyboard_typing", "other_voice"], 2, 3)
    assert "键盘" in second and "其他人说话" in second and "最后一次提醒" in second
    assert "多次违规" in ending_text()
    assert "violation 2" in warning_text(["phone"], 2, 3, "en")


class _Typing:
    accepts_audio = True

    def describe(self, *, system, jpeg, wav=None, note=""):
        return json.dumps({"flags": ["keyboard_typing"], "detail": "持续的键盘敲击声"})


class _Bridge:
    prompts: list[str] = []

    def __init__(self, **_kwargs): pass
    async def connect(self): pass
    async def events(self): await asyncio.Event().wait()
    async def trigger_response(self, instructions=""): _Bridge.prompts.append(instructions)
    async def send_audio(self, pcm): pass
    async def send_image(self, jpeg): pass
    async def close(self): pass


def test_websocket_warns_then_ends_the_interview(client, db_session, monkeypatch):
    from app.core.proctor import ProctorMonitor

    job = models.Job(title="后端", jd="x", interviewer_voice="Tina")
    cand = models.Candidate(name="赵六")
    db_session.add_all([job, cand])
    db_session.commit()
    db_session.add(models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token="tok-typing"))
    db_session.commit()

    _Bridge.prompts = []
    monkeypatch.setattr("app.api.interview_ws.bridge_factory", _Bridge)
    monkeypatch.setattr("app.api.interview_ws.ai_detector_factory", lambda: object())
    monkeypatch.setattr("app.api.interview_ws.proctor_factory", lambda: VisionProctor(_Typing()))
    monkeypatch.setattr("app.api.interview_ws.ProctorMonitor", lambda: ProctorMonitor(cooldown_s=0))
    monkeypatch.setattr("app.api.interview_ws.FAREWELL_SECONDS", 0.01)
    real_sleep = asyncio.sleep

    async def fast_sleep(seconds):
        await real_sleep(0.03 if seconds >= 1 else seconds)

    monkeypatch.setattr("app.api.interview_ws.asyncio.sleep", fast_sleep)

    second = struct.pack("<16000h", *([3000, -3000] * 8000))

    def message(kind, payload):
        return json.dumps({"type": kind, "data": base64.b64encode(payload).decode()})

    received = []
    with client.websocket_connect("/ws/interview?token=tok-typing") as ws:
        try:
            for n in range(400):
                for _ in range(3):
                    ws.send_text(message("proctor_audio", second))
                ws.send_text(message("image", b"frame-%d" % n))
                import time; time.sleep(0.02)
                if any("多次违规" in p for p in _Bridge.prompts):
                    break
            while True:
                received.append(ws.receive_json())
        except Exception:
            pass  # the server hung up, which is the point

    warnings = [p for p in _Bridge.prompts if "次违规,累计" in p]
    assert len(warnings) == 2
    assert "多次违规" in _Bridge.prompts[-1]
    assert {"type": "error", "message": "监考多次检测到违规行为，属于多次违规，本次面试已结束。"} in received

    db_session.expire_all()
    kinds = [e.kind for e in db_session.query(models.CheatEvent).all()]
    assert kinds.count("keyboard_typing") == 3
    assert kinds[-1] == "repeated_violation"
