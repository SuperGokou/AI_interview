from app.core.cheat_store import record_cheat_event
from app.db import models


def _seed_session(db_session, token="tok-c"):
    job = models.Job(title="后端", jd="x")
    db_session.add(job)
    db_session.commit()
    cand = models.Candidate(name="张三")
    db_session.add(cand)
    db_session.commit()
    sess = models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token=token)
    db_session.add(sess)
    db_session.commit()
    return sess.id


def test_cheat_endpoint_empty_is_green(client, db_session):
    _seed_session(db_session)
    body = client.get("/api/sessions/tok-c/cheat").json()
    assert body["integrity_level"] == "green"
    assert body["events"] == []


def test_cheat_endpoint_lists_events_and_red_level(client, db_session):
    sid = _seed_session(db_session)
    record_cheat_event(db_session, sid, kind="multi_person", severity="high", evidence="画面两人")
    body = client.get("/api/sessions/tok-c/cheat").json()
    assert body["integrity_level"] == "red"
    assert len(body["events"]) == 1
    assert body["events"][0]["kind"] == "multi_person"
    assert body["events"][0]["severity"] == "high"
    assert body["events"][0]["evidence"] == "画面两人"


def test_cheat_endpoint_unknown_token_404(client):
    assert client.get("/api/sessions/nope/cheat").status_code == 404
