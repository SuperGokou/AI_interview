from app.db import models


class _FakeGen:
    def __init__(self):
        self.captured = None

    def generate(self, **kwargs):
        self.captured = kwargs
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
    gen = _FakeGen()
    monkeypatch.setattr("app.api.sessions.report_generator_factory", lambda: gen)
    resp = client.post("/api/sessions/tok-r/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["score_professional"] == 88
    assert body["overall"] == "建议录用"
    # generator fed JD + transcript
    assert "JD写后端XYZ" in gen.captured["jd"]
    assert any("我的回答ABC" in t["text"] for t in gen.captured["transcripts"])
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


def test_create_report_twice_upserts_single_row(client, db_session, monkeypatch):
    sid = _seed(db_session, token="tok-r4")
    monkeypatch.setattr("app.api.sessions.report_generator_factory", lambda: _FakeGen())
    assert client.post("/api/sessions/tok-r4/report").status_code == 200
    assert client.post("/api/sessions/tok-r4/report").status_code == 200
    db_session.expire_all()
    rows = db_session.query(models.Report).filter_by(session_id=sid).all()
    assert len(rows) == 1


def test_bad_model_output_returns_retryable_error_without_report(client, db_session, monkeypatch):
    sid = _seed(db_session, token="bad-report")
    class Bad:
        def generate(self, **kwargs): raise ValueError('bad model JSON')
    monkeypatch.setattr('app.api.sessions.report_generator_factory', Bad)
    response = client.post('/api/sessions/bad-report/report')
    assert response.status_code == 502
    assert db_session.query(models.Report).filter_by(session_id=sid).count() == 0


def test_report_endpoint_reports_an_unreachable_model_as_502(client, db_session, monkeypatch):
    """A rejected key or network failure must not surface as a bare 500."""
    from app.db import models

    class _Unreachable:
        def generate(self, **_kwargs):
            raise RuntimeError("401 Authentication Fails")

    job = models.Job(title="后端", jd="x", interviewer_voice="Tina")
    cand = models.Candidate(name="张三")
    db_session.add_all([job, cand])
    db_session.commit()
    db_session.add(models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token="tok-502"))
    db_session.commit()
    monkeypatch.setattr("app.api.sessions.report_generator_factory", lambda: _Unreachable())
    resp = client.post("/api/sessions/tok-502/report")
    assert resp.status_code == 502
    assert "评估模型调用失败" in resp.json()["detail"]
    assert "401" not in resp.text  # provider error text stays in the server log
