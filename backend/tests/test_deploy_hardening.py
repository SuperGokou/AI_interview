"""Regression tests for the pre-deployment hardening pass."""

import asyncio

import pytest
from sqlalchemy.exc import OperationalError

from app.db import models
from app.db.base import get_db
from app.main import app
from app.security import AUTH_FAILURE_LIMIT

JOB = {"title": "后端工程师", "jd": "负责后端", "interviewer_voice": "Tina", "language": "zh"}


def _seed_session(db, *, token, status="pending", duration=30):
    job = models.Job(title="后端", jd="x", interviewer_voice="Tina", duration_minutes=duration)
    cand = models.Candidate(name="张三")
    db.add_all([job, cand])
    db.commit()
    sess = models.InterviewSession(
        job_id=job.id, candidate_id=cand.id, link_token=token, status=status
    )
    db.add(sess)
    db.commit()
    return sess.id


# --- admin boundary -------------------------------------------------------


def test_admin_write_allowed_behind_tls_terminating_proxy(client):
    """Caddy terminates TLS: the browser Origin is https while the app sees http."""
    resp = client.post("/api/jobs", headers={"Origin": "https://testserver"}, json=JOB)
    assert resp.status_code == 200, resp.text


def test_cross_origin_write_still_denied(client):
    resp = client.post("/api/jobs", headers={"Origin": "https://evil.example"}, json=JOB)
    assert resp.status_code == 403


def test_repeated_wrong_passwords_are_throttled(client):
    client.auth = ("admin", "wrong")
    for _ in range(AUTH_FAILURE_LIMIT):
        assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/jobs").status_code == 429
    # Even the right password is refused while the window is open.
    client.auth = ("admin", "test-only-admin-password")
    assert client.get("/api/jobs").status_code == 429


def test_anonymous_visits_do_not_trip_the_throttle(client):
    client.auth = None
    for _ in range(AUTH_FAILURE_LIMIT + 5):
        assert client.get("/api/jobs").status_code == 401
    client.auth = ("admin", "test-only-admin-password")
    assert client.get("/api/jobs").status_code == 200


def test_security_headers_present(client):
    headers = client.get("/interview").headers
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" not in client.get("/docs").headers


# --- health ---------------------------------------------------------------


def test_health_reports_503_when_database_is_down(client):
    class _Broken:
        def execute(self, *_a, **_k):
            raise OperationalError("SELECT 1", {}, Exception("down"))

    app.dependency_overrides[get_db] = lambda: _Broken()
    resp = client.get("/api/health")
    assert resp.status_code == 503
    assert resp.json()["database"] == "down"


# --- static caching -------------------------------------------------------


def test_static_cache_policy(client, monkeypatch, tmp_path):
    import app.main as main

    (tmp_path / "index.html").write_text("shell")
    (tmp_path / "clip.webm").write_text("video")
    monkeypatch.setattr(main, "FRONTEND_DIR", tmp_path)
    assert client.get("/interview").headers["cache-control"] == "no-cache"
    assert "max-age=86400" in client.get("/clip.webm").headers["cache-control"]


# --- validation and data integrity ---------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"duration_minutes": 0},
        {"duration_minutes": 100000},
        {"interviewer_voice": "NotAVoice"},
        {"language": "fr"},
        {"title": ""},
        {"title": "x" * 200},
    ],
)
def test_job_input_is_validated(client, override):
    assert client.post("/api/jobs", json={**JOB, **override}).status_code == 422


def test_blank_candidate_name_rejected(client):
    job = client.post("/api/jobs", json=JOB).json()
    resp = client.post("/api/sessions", json={"job_id": job["id"], "candidate_name": "   "})
    assert resp.status_code == 422


def test_job_with_interviews_cannot_be_deleted(client):
    job = client.post("/api/jobs", json=JOB).json()
    client.post("/api/sessions", json={"job_id": job["id"], "candidate_name": "张三"})
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 409
    assert client.get(f"/api/jobs/{job['id']}").status_code == 200


def test_dashboard_counts_jobs_created_by_admin_ui(client):
    """The admin UI stores status "active"; it used to be counted as zero open jobs."""
    client.post("/api/jobs", json={**JOB, "status": "active"})
    client.post("/api/jobs", json={**JOB, "status": "draft"})
    assert client.get("/api/dashboard/stats").json()["active_jobs"] == 1


def test_overall_score_is_mean_of_dimensions(client, db_session):
    sid = _seed_session(db_session, token="tok-score", status="done")
    db_session.add(
        models.Report(
            session_id=sid, score_professional=90, score_communication=60,
            score_job_match=60, ai_risk_level="high",
        )
    )
    db_session.commit()
    row = client.get("/api/sessions").json()[0]
    assert row["score_overall"] == 70
    assert client.get("/api/dashboard/stats").json()["high_risk"] == 1


def test_consent_timestamp_is_not_overwritten(client, db_session):
    _seed_session(db_session, token="tok-consent")
    client.post("/api/sessions/tok-consent/consent")
    db_session.expire_all()
    first = db_session.query(models.InterviewSession).one().consented_at
    client.post("/api/sessions/tok-consent/consent")
    db_session.expire_all()
    assert db_session.query(models.InterviewSession).one().consented_at == first


# --- interview websocket --------------------------------------------------


class _Bridge:
    """Emits the class-level events, then idles."""

    events_to_emit: list[dict] = []
    fail_connect = False
    audio: list[bytes] = []

    def __init__(self, **_kwargs):
        self._pending = list(type(self).events_to_emit)

    async def connect(self):
        if type(self).fail_connect:
            raise RuntimeError("provider unavailable")

    async def events(self):
        if self._pending:
            return self._pending.pop(0)
        await asyncio.Event().wait()

    async def trigger_response(self, instructions=""):
        pass

    async def send_audio(self, pcm):
        type(self).audio.append(pcm)

    async def send_image(self, jpeg):
        pass

    async def close(self):
        pass


class _Reports:
    calls = 0

    def generate(self, **_kwargs):
        type(self).calls += 1
        return {
            "score_professional": 1, "score_communication": 1, "score_job_match": 1,
            "score_demeanor": None, "ai_risk_level": "low", "feedback": "f", "overall": "o",
        }


@pytest.fixture
def ws_fakes(monkeypatch):
    _Bridge.events_to_emit, _Bridge.fail_connect, _Bridge.audio = [], False, []
    _Reports.calls = 0
    monkeypatch.setattr("app.api.interview_ws.bridge_factory", _Bridge)
    monkeypatch.setattr("app.api.interview_ws.report_generator_factory", _Reports)
    monkeypatch.setattr("app.api.interview_ws.ai_detector_factory", lambda: object())


def test_finished_interview_link_cannot_be_replayed(client, db_session, ws_fakes):
    _seed_session(db_session, token="tok-done", status="done")
    with client.websocket_connect("/ws/interview?token=tok-done") as ws:
        assert ws.receive_json()["type"] == "error"
    assert _Reports.calls == 0


def test_model_connection_failure_is_reported_and_invite_stays_usable(
    client, db_session, ws_fakes
):
    _seed_session(db_session, token="tok-down")
    _Bridge.fail_connect = True
    with client.websocket_connect("/ws/interview?token=tok-down") as ws:
        assert ws.receive_json()["type"] == "error"
    db_session.expire_all()
    assert db_session.query(models.InterviewSession).one().status == "pending"


def test_failing_detector_does_not_stop_the_interviewer(client, db_session, ws_fakes, monkeypatch):
    class _Boom:
        def detect(self, _text):
            raise RuntimeError("scoring provider down")

    monkeypatch.setattr("app.api.interview_ws.ai_detector_factory", lambda: _Boom())
    _seed_session(db_session, token="tok-boom")
    _Bridge.events_to_emit = [
        {"kind": "user_transcript", "text": "我的回答"},
        {"kind": "transcript", "text": "下一个问题"},
    ]
    with client.websocket_connect("/ws/interview?token=tok-boom") as ws:
        assert ws.receive_json()["type"] == "user_transcript"
        assert ws.receive_json() == {"type": "transcript", "text": "下一个问题"}


def test_malformed_frames_are_ignored(client, db_session, ws_fakes):
    _seed_session(db_session, token="tok-junk")
    _Bridge.events_to_emit = [{"kind": "transcript", "text": "你好"}]
    with client.websocket_connect("/ws/interview?token=tok-junk") as ws:
        ws.send_text("not json")
        ws.send_json({"type": "audio", "data": "***not-base64***"})
        ws.send_json({"type": "unknown", "data": "AAAA"})
        ws.send_json({"type": "audio", "data": "AAEC"})
        assert ws.receive_json()["type"] == "transcript"
    assert _Bridge.audio == [b"\x00\x01\x02"]


def test_empty_interview_does_not_spend_a_report_call(client, db_session, ws_fakes):
    _seed_session(db_session, token="tok-empty")
    with client.websocket_connect("/ws/interview?token=tok-empty"):
        pass
    db_session.expire_all()
    assert db_session.query(models.InterviewSession).one().status == "done"
    assert _Reports.calls == 0


def test_interview_is_closed_at_the_time_limit(client, db_session, ws_fakes, monkeypatch):
    monkeypatch.setattr("app.api.interview_ws._OVERTIME_GRACE_S", -59.9)
    _seed_session(db_session, token="tok-late", duration=1)
    with client.websocket_connect("/ws/interview?token=tok-late") as ws:
        frame = ws.receive_json()
        assert frame["type"] == "error" and "时间已到" in frame["message"]
    db_session.expire_all()
    assert db_session.query(models.InterviewSession).one().status == "done"
