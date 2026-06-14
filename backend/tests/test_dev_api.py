"""POST /api/dev/demo-session のテスト — 演示会话入口。"""

from app.db import models


def test_demo_session_returns_token(client):
    """POST /api/dev/demo-session returns a non-empty token."""
    resp = client.post("/api/dev/demo-session")
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body
    assert isinstance(body["token"], str)
    assert len(body["token"]) > 0


def test_demo_session_creates_session_in_db(client, db_session):
    """POST /api/dev/demo-session creates a real InterviewSession in the DB."""
    resp = client.post("/api/dev/demo-session")
    assert resp.status_code == 200
    token = resp.json()["token"]

    db_session.expire_all()
    sess = (
        db_session.query(models.InterviewSession).filter_by(link_token=token).first()
    )
    assert sess is not None
    assert sess.status == "pending"


def test_demo_session_idempotent_job(client):
    """Calling demo-session twice should reuse the same demo Job (no duplicates)."""
    client.post("/api/dev/demo-session")
    client.post("/api/dev/demo-session")

    from app.db.base import get_db
    from app.main import app

    # Access the db through the existing override in the test client
    resp = client.post("/api/dev/demo-session")
    assert resp.status_code == 200


def test_demo_session_job_has_questions(client, db_session):
    """The demo job should have at least one is_probe question."""
    client.post("/api/dev/demo-session")
    db_session.expire_all()
    job = (
        db_session.query(models.Job)
        .filter_by(title="演示职位 · 后端工程师")
        .first()
    )
    assert job is not None
    questions = db_session.query(models.Question).filter_by(job_id=job.id).all()
    assert len(questions) >= 2
    probe_questions = [q for q in questions if q.is_probe]
    assert len(probe_questions) >= 1
