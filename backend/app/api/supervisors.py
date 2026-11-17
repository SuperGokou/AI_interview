"""Supervisor links and session-scoped transcript access for the new frontend."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.sessions import _get_session_or_404, list_transcripts
from app.core.cheat_store import list_cheat_events
from app.core.integrity import compute_integrity_level
from app.core.live_frames import live_frames
from app.core.tokens import generate_link_token
from app.db import models
from app.db.base import get_db

router = APIRouter(prefix="/api")


class CreateLinks(BaseModel):
    count: int = Field(default=1, ge=1, le=10)
    labels: list[str] | None = Field(default=None, min_length=1, max_length=10)


def _links(db, session_id):
    return db.query(models.SupervisorLink).filter_by(session_id=session_id).order_by(models.SupervisorLink.id).all()


def _out(link):
    return {"token": link.token, "label": link.label, "created_at": link.created_at.isoformat()}


@router.post('/sessions/{token}/supervisors')
def create_links(token: str, body: CreateLinks, db: Session = Depends(get_db)):
    sess = _get_session_or_404(token, db)
    labels = body.labels or [f"监督员 {i + 1}" for i in range(body.count)]
    if any(not label.strip() or len(label.strip()) > 64 for label in labels):
        raise HTTPException(422, "labels must contain 1–64 characters")
    links = [models.SupervisorLink(session_id=sess.id, token=generate_link_token(), label=label.strip()) for label in labels]
    db.add_all(links)
    db.commit()
    # Refresh to serialize database timestamps consistently on subsequent reads.
    for link in links:
        db.refresh(link)
    return {"session_token": token, "links": [_out(link) for link in links]}


@router.get('/sessions/{token}/supervisors')
def list_links(token: str, db: Session = Depends(get_db)):
    sess = _get_session_or_404(token, db)
    return [_out(link) for link in _links(db, sess.id)]


def _resolve(db, token):
    link = db.query(models.SupervisorLink).filter_by(token=token).first()
    sess = db.get(models.InterviewSession, link.session_id) if link else None
    if not sess:
        raise HTTPException(404, "supervisor link not found")
    return link, sess


@router.get('/supervisors/{token}')
def get_supervisor(token: str, db: Session = Depends(get_db)):
    link, sess = _resolve(db, token)
    return {
        "supervisor_token": token,
        "label": link.label,
        # Never expose the candidate bearer token to a supervisor.
        "session_token": "",
        "status": sess.status,
        "candidate_name": sess.candidate.name,
        "job": {"title": sess.job.title, "language": sess.job.language,
                "duration_minutes": sess.job.duration_minutes, "interviewer_voice": sess.job.interviewer_voice},
        "supervisors": [{"label": p.label, "is_current": p.id == link.id} for p in _links(db, sess.id)],
    }


@router.get('/supervisors/{token}/transcripts')
def supervisor_transcripts(token: str, db: Session = Depends(get_db)):
    _, sess = _resolve(db, token)
    events = list_cheat_events(db, sess.id)
    return {"status": sess.status, "live": sess.status in ('active', 'done', 'in_progress', 'completed'),
            "transcripts": list_transcripts(sess.link_token, db),
            # What proctoring has noticed so far, so the supervisor sees it as it happens.
            "integrity_level": compute_integrity_level(events),
            "events": [{"kind": e.kind, "severity": e.severity, "evidence": e.evidence,
                        "ts": e.ts.isoformat() if e.ts else None} for e in events]}


@router.get('/supervisors/{token}/frame')
def supervisor_frame(token: str, db: Session = Depends(get_db)):
    """The candidate's newest camera frame, for the live view. 204 when there is none."""
    _, sess = _resolve(db, token)
    jpeg = live_frames.get(sess.id) if sess.status == 'active' else None
    if jpeg is None:
        return Response(status_code=204)
    return Response(content=jpeg, media_type="image/jpeg")
