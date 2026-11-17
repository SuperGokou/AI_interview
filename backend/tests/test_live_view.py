"""Supervisors see the candidate live; findings keep the frame they were based on."""

import asyncio
import base64
import json

from app.core.live_frames import LiveFrames, live_frames
from app.core.proctor import VisionProctor
from app.db import models


def test_live_frames_expire_and_are_dropped():
    now = [0.0]
    frames = LiveFrames(stale_after_s=15, clock=lambda: now[0])
    assert frames.get(1) is None
    frames.put(1, b"a")
    now[0] = 10
    assert frames.get(1) == b"a"
    now[0] = 16
    assert frames.get(1) is None  # the camera was switched off
    frames.put(1, b"b")
    frames.drop(1)
    assert frames.get(1) is None


def _session(db_session, token, status="pending"):
    job = models.Job(title="后端", jd="x", interviewer_voice="Tina")
    cand = models.Candidate(name="周八")
    db_session.add_all([job, cand])
    db_session.commit()
    sess = models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token=token, status=status)
    db_session.add(sess)
    db_session.commit()
    db_session.add(models.SupervisorLink(session_id=sess.id, token=f"sup-{token}", label="监督员 1"))
    db_session.commit()
    return sess


def test_supervisor_gets_the_newest_frame_only_while_the_interview_is_live(client, db_session):
    sess = _session(db_session, "tok-live", status="active")
    assert client.get("/api/supervisors/sup-tok-live/frame").status_code == 204
    live_frames.put(sess.id, b"jpeg-bytes")
    try:
        response = client.get("/api/supervisors/sup-tok-live/frame")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content == b"jpeg-bytes"
        sess.status = "done"
        db_session.commit()
        assert client.get("/api/supervisors/sup-tok-live/frame").status_code == 204
    finally:
        live_frames.drop(sess.id)
    assert client.get("/api/supervisors/no-such-link/frame").status_code == 404


def test_supervisor_feed_includes_what_proctoring_noticed(client, db_session):
    sess = _session(db_session, "tok-feed", status="active")
    db_session.add(models.CheatEvent(session_id=sess.id, kind="phone", severity="high", evidence="手持手机"))
    db_session.commit()
    feed = client.get("/api/supervisors/sup-tok-feed/transcripts").json()
    assert feed["integrity_level"] == "red"
    assert [(e["kind"], e["severity"]) for e in feed["events"]] == [("phone", "high")]


class _Vision:
    def describe(self, *, system, jpeg):
        return json.dumps({"flags": ["phone"], "detail": "手持手机"})


class _Bridge:
    def __init__(self, **_kwargs): pass
    async def connect(self): pass
    async def events(self): await asyncio.Event().wait()
    async def trigger_response(self, instructions=""): pass
    async def cancel_response(self): pass
    async def send_audio(self, pcm): pass
    async def send_image(self, jpeg): pass
    async def close(self): pass


def test_a_finding_keeps_its_frame_and_only_admins_can_fetch_it(client, db_session, monkeypatch):
    _session(db_session, "tok-snap")
    monkeypatch.setattr("app.api.interview_ws.bridge_factory", _Bridge)
    monkeypatch.setattr("app.api.interview_ws.ai_detector_factory", lambda: object())
    monkeypatch.setattr("app.api.interview_ws.proctor_factory", lambda: VisionProctor(_Vision()))
    real_sleep = asyncio.sleep

    async def fast_sleep(seconds):
        await real_sleep(0.03 if seconds >= 0.5 else seconds)

    monkeypatch.setattr("app.api.interview_ws.asyncio.sleep", fast_sleep)

    picture = bytes([0xFF, 0xD8]) + b" the frame with the phone in it"
    with client.websocket_connect("/ws/interview?token=tok-snap") as ws:
        ws.send_text(json.dumps({"type": "image", "data": base64.b64encode(picture).decode()}))
        assert ws.receive_json() == {"type": "integrity", "level": "red"}

    events = client.get("/api/sessions/tok-snap/cheat").json()["events"]
    assert [(e["kind"], e["snapshot"]) for e in events] == [("phone", True)]
    url = f"/api/sessions/tok-snap/cheat/{events[0]['id']}/snapshot"
    response = client.get(url)
    assert response.status_code == 200 and response.content == picture
    assert client.get("/api/sessions/tok-snap/cheat/999999/snapshot").status_code == 404


def test_snapshot_route_is_not_public():
    from app.security import _is_public

    assert _is_public("GET", "/api/supervisors/abc/frame")
    assert not _is_public("GET", "/api/sessions/abc/cheat/1/snapshot")
    assert not _is_public("GET", "/api/sessions/abc/cheat")
