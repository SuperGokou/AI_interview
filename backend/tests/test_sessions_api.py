from app.db import models


def _make_job(db_session, **kw):
    job = models.Job(
        title=kw.get("title", "后端工程师"),
        jd=kw.get("jd", "负责后端服务开发"),
        language=kw.get("language", "zh"),
        duration_minutes=kw.get("duration_minutes", 30),
        interviewer_voice=kw.get("interviewer_voice", "Tina"),
    )
    db_session.add(job)
    db_session.commit()
    return job


def test_create_session_returns_token(client, db_session):
    job = _make_job(db_session)
    resp = client.post("/api/sessions", json={"job_id": job.id, "candidate_name": "张三"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    assert body["status"] == "pending"


def test_create_session_unknown_job_404(client):
    resp = client.post("/api/sessions", json={"job_id": 9999, "candidate_name": "李四"})
    assert resp.status_code == 404


def test_get_session_returns_job_summary(client, db_session):
    job = _make_job(db_session, title="算法工程师", interviewer_voice="Ethan")
    token = client.post(
        "/api/sessions", json={"job_id": job.id, "candidate_name": "王五"}
    ).json()["token"]
    resp = client.get(f"/api/sessions/{token}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["candidate_name"] == "王五"
    assert body["consented"] is False
    assert body["job"]["title"] == "算法工程师"
    assert body["job"]["interviewer_voice"] == "Ethan"


def test_get_session_unknown_404(client):
    assert client.get("/api/sessions/nope").status_code == 404


def test_consent_marks_session(client, db_session):
    job = _make_job(db_session)
    token = client.post(
        "/api/sessions", json={"job_id": job.id, "candidate_name": "赵六"}
    ).json()["token"]
    assert client.post(f"/api/sessions/{token}/consent").status_code == 200
    assert client.get(f"/api/sessions/{token}").json()["consented"] is True
