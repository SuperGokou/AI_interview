from app.db import models


class _FakeGen:
    def generate(self, **kwargs):
        _FakeGen.captured = kwargs
        return {
            "score_professional": 88,
            "score_communication": 80,
            "score_job_match": 85,
            "score_demeanor": None,
            "ai_risk_level": "low",
            "feedback": "专业扎实",
            "overall": "建议录用",
        }


def _seed(db_session, token="tok-r"):
    job = models.Job(title="后端工程师", jd="JD写后端XYZ")
    db_session.add(job)
    db_session.commit()
    db_session.add(models.Question(job_id=job.id, prompt="索引?", key_points="B+树",
                                   reference_answer="...", difficulty="中级"))
    db_session.commit()
    cand = models.Candidate(name="张三")
    db_session.add(cand)
    db_session.commit()
    sess = models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token=token)
    db_session.add(sess)
    db_session.commit()
    db_session.add(models.Transcript(session_id=sess.id, role="candidate", text="我的回答ABC"))
    db_session.commit()
    return sess.id


def test_create_report_generates_and_persists(client, db_session, monkeypatch):
    sid = _seed(db_session)
    monkeypatch.setattr("app.api.sessions.report_generator_factory", lambda: _FakeGen())
    resp = client.post("/api/sessions/tok-r/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["score_professional"] == 88
    assert body["overall"] == "建议录用"
    # generator fed JD + transcript
    assert "JD写后端XYZ" in _FakeGen.captured["jd"]
    assert any("我的回答ABC" in t["text"] for t in _FakeGen.captured["transcripts"])
    # persisted
    db_session.expire_all()
    r = db_session.query(models.Report).filter_by(session_id=sid).first()
    assert r is not None and r.score_professional == 88


def test_get_report_404_when_absent(client, db_session):
    _seed(db_session, token="tok-r2")
    assert client.get("/api/sessions/tok-r2/report").status_code == 404


def test_get_report_after_create(client, db_session, monkeypatch):
    _seed(db_session, token="tok-r3")
    monkeypatch.setattr("app.api.sessions.report_generator_factory", lambda: _FakeGen())
    client.post("/api/sessions/tok-r3/report")
    body = client.get("/api/sessions/tok-r3/report").json()
    assert body["ai_risk_level"] == "low"


def test_create_report_unknown_token_404(client):
    assert client.post("/api/sessions/nope/report").status_code == 404
