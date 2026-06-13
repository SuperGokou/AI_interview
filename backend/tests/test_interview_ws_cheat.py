import asyncio

from app.db import models


def _seed(db_session, token="tok-cheat"):
    job = models.Job(title="后端", jd="x", interviewer_voice="Tina", language="zh")
    db_session.add(job)
    db_session.commit()
    db_session.add(models.Question(job_id=job.id, prompt="什么是索引?", difficulty="中级"))
    db_session.commit()
    cand = models.Candidate(name="张三")
    db_session.add(cand)
    db_session.commit()
    sess = models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token=token)
    db_session.add(sess)
    db_session.commit()
    return sess.id


class _FakeBridge:
    _events = [
        {"kind": "vision", "flags": ["multi_person"], "detail": "画面两人"},
        {"kind": "user_transcript", "text": "一段非常结构化、面面俱到的标准答案"},
    ]

    def __init__(self, **kwargs):
        self._i = 0

    async def connect(self):
        pass

    async def events(self):
        if self._i < len(self._events):
            ev = self._events[self._i]
            self._i += 1
            return ev
        await asyncio.Event().wait()

    async def trigger_response(self, instructions=""):
        pass

    async def send_audio(self, pcm):
        pass

    async def send_image(self, jpeg):
        pass

    async def close(self):
        pass


class _FakeDetector:
    def detect(self, text):
        return {"is_ai_like": True, "confidence": 0.9, "reason": "教科书腔"}


def test_ws_records_vision_and_ai_text_cheat_events(client, db_session, monkeypatch):
    sid = _seed(db_session)
    monkeypatch.setattr("app.api.interview_ws.bridge_factory", _FakeBridge)
    monkeypatch.setattr("app.api.interview_ws.ai_detector_factory", lambda: _FakeDetector())

    with client.websocket_connect("/ws/interview?token=tok-cheat") as ws:
        # vision → integrity 帧;user_transcript 帧;ai_text → integrity 帧
        frames = [ws.receive_json() for _ in range(3)]

    types = [f["type"] for f in frames]
    assert types.count("integrity") == 2
    assert "user_transcript" in types

    db_session.expire_all()
    kinds = {e.kind for e in db_session.query(models.CheatEvent).filter_by(session_id=sid).all()}
    assert "multi_person" in kinds
    assert "ai_text" in kinds

    body = client.get("/api/sessions/tok-cheat/cheat").json()
    assert body["integrity_level"] == "red"
