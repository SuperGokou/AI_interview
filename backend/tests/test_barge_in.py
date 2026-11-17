"""The candidate talks over the interviewer: it stops, as a person would."""

import asyncio

from app.db import models


class _Bridge:
    instance = None

    def __init__(self, **_kwargs):
        _Bridge.instance = self
        self.queue = asyncio.Queue()
        self.cancelled = 0

    async def connect(self): pass
    async def events(self): return await self.queue.get()
    async def trigger_response(self, instructions=""): pass
    async def cancel_response(self): self.cancelled += 1
    async def send_audio(self, pcm): pass
    async def send_image(self, jpeg): pass
    async def close(self): pass


def _session(db_session, token):
    job = models.Job(title="后端", jd="x", interviewer_voice="Tina")
    cand = models.Candidate(name="孙七")
    db_session.add_all([job, cand])
    db_session.commit()
    db_session.add(models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token=token))
    db_session.commit()


def _settings(monkeypatch, hold_ms):
    from dataclasses import replace

    from app.api import interview_ws
    from app.config import get_settings

    tuned = replace(get_settings(), barge_in_hold_ms=hold_ms)
    monkeypatch.setattr(interview_ws, "get_settings", lambda: tuned)
    monkeypatch.setattr(interview_ws, "bridge_factory", _Bridge)
    monkeypatch.setattr(interview_ws, "ai_detector_factory", lambda: object())


LONG_REPLY = bytes(24000 * 2 * 20)  # 20 s of interviewer audio


def test_sustained_speech_over_the_interviewer_stops_the_reply(client, db_session, monkeypatch):
    _session(db_session, "tok-barge")
    _settings(monkeypatch, hold_ms=30)
    with client.websocket_connect("/ws/interview?token=tok-barge") as ws:
        bridge = _Bridge.instance
        bridge.queue.put_nowait({"kind": "audio", "data": LONG_REPLY})
        assert ws.receive_json()["type"] == "audio"
        bridge.queue.put_nowait({"kind": "speech_started"})
        assert ws.receive_json() == {"type": "interrupt"}
        assert bridge.cancelled == 1
        # What the model still sends for the cut reply is not played...
        bridge.queue.put_nowait({"kind": "audio", "data": LONG_REPLY})
        bridge.queue.put_nowait({"kind": "response_done"})
        # ...and the next reply starts a new utterance.
        bridge.queue.put_nowait({"kind": "audio", "data": bytes(4800)})
        following = ws.receive_json()
        assert (following["type"], following["u"], following["p"]) == ("audio", 1, 0)


def test_a_cough_does_not_interrupt(client, db_session, monkeypatch):
    _session(db_session, "tok-cough")
    _settings(monkeypatch, hold_ms=300)
    with client.websocket_connect("/ws/interview?token=tok-cough") as ws:
        bridge = _Bridge.instance
        bridge.queue.put_nowait({"kind": "audio", "data": LONG_REPLY})
        assert ws.receive_json()["type"] == "audio"
        bridge.queue.put_nowait({"kind": "speech_started"})
        bridge.queue.put_nowait({"kind": "speech_stopped"})
        bridge.queue.put_nowait({"kind": "transcript", "text": "接着说"})
        assert ws.receive_json() == {"type": "transcript", "text": "接着说"}
        assert bridge.cancelled == 0
