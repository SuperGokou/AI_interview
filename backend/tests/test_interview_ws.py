import asyncio

from app.db import models


def _seed(db_session, *, token="tok-abc", voice="Ethan"):
    job = models.Job(title="后端工程师", jd="负责后端", interviewer_voice=voice, language="zh")
    db_session.add(job)
    db_session.commit()
    db_session.add(models.Question(job_id=job.id, prompt="什么是数据库索引?", difficulty="中级"))
    db_session.commit()
    cand = models.Candidate(name="张三")
    db_session.add(cand)
    db_session.commit()
    sess = models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token=token)
    db_session.add(sess)
    db_session.commit()
    return sess.id


class _FakeBridge:
    """记录构造参数,首个 events() 推一条 transcript,之后阻塞直到被取消。"""

    def __init__(self, **kwargs):
        _FakeBridge.captured = kwargs
        self._emitted = False

    async def connect(self):
        pass

    async def events(self):
        if not self._emitted:
            self._emitted = True
            return {"kind": "transcript", "text": "你好,我是面试官"}
        await asyncio.Event().wait()

    async def trigger_response(self, instructions=""):
        pass

    async def send_audio(self, pcm):
        pass

    async def send_image(self, jpeg):
        pass

    async def close(self):
        pass


def test_ws_persists_transcript_and_injects_question_bank(client, db_session, monkeypatch):
    sess_id = _seed(db_session)
    monkeypatch.setattr("app.api.interview_ws.bridge_factory", _FakeBridge)

    with client.websocket_connect("/ws/interview?token=tok-abc") as ws:
        frame = ws.receive_json()
        assert frame["type"] == "transcript"
        assert frame["text"] == "你好,我是面试官"

    # 注入的 instructions 含题库与正确音色
    assert _FakeBridge.captured["voice"] == "Ethan"
    assert "什么是数据库索引?" in _FakeBridge.captured["instructions"]

    # 转写已落库(面试官角色)
    db_session.expire_all()
    rows = db_session.query(models.Transcript).filter_by(session_id=sess_id).all()
    assert any(r.role == "interviewer" and r.text == "你好,我是面试官" for r in rows)


def test_ws_invalid_token_sends_error(client):
    with client.websocket_connect("/ws/interview?token=does-not-exist") as ws:
        frame = ws.receive_json()
        assert frame["type"] == "error"
