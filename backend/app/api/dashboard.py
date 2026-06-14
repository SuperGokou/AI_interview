"""仪表盘统计 REST(单一职责:聚合指标 + 最近会话)。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.cheat_store import list_cheat_events
from app.core.integrity import compute_integrity_level
from app.db import models
from app.db.base import get_db

router = APIRouter(prefix="/api/dashboard")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class SessionListItem(BaseModel):
    token: str
    candidate_name: str
    job_title: str
    status: str
    integrity_level: str
    score_overall: int | None
    created_at: str | None


class DashboardStats(BaseModel):
    active_jobs: int
    pending_interviews: int
    completed_interviews: int
    high_risk: int
    recent: list[SessionListItem]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_to_item(sess: models.InterviewSession, db: Session) -> SessionListItem:
    candidate = db.get(models.Candidate, sess.candidate_id)
    job = db.get(models.Job, sess.job_id)
    events = list_cheat_events(db, sess.id)
    integrity_level = compute_integrity_level(events)
    report = db.query(models.Report).filter_by(session_id=sess.id).first()
    score_overall = report.score_professional if report else None
    raw_ts = sess.started_at or sess.consented_at
    created_at = raw_ts.isoformat() if raw_ts else None
    return SessionListItem(
        token=sess.link_token,
        candidate_name=candidate.name if candidate else "",
        job_title=job.title if job else "",
        status=sess.status,
        integrity_level=integrity_level,
        score_overall=score_overall,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=DashboardStats)
def get_stats(db: Session = Depends(get_db)):
    active_jobs = (
        db.query(models.Job).filter(models.Job.status == "招聘中").count()
    )

    pending_interviews = (
        db.query(models.InterviewSession)
        .filter(models.InterviewSession.status.in_(["pending", "active"]))
        .count()
    )

    completed_interviews = (
        db.query(models.InterviewSession)
        .filter(models.InterviewSession.status == "done")
        .count()
    )

    # High-risk: sessions with red integrity level OR a high-risk report
    all_sessions = db.query(models.InterviewSession).all()
    high_risk = 0
    for sess in all_sessions:
        events = list_cheat_events(db, sess.id)
        level = compute_integrity_level(events)
        if level == "red":
            high_risk += 1
            continue
        report = db.query(models.Report).filter_by(session_id=sess.id).first()
        if report and report.ai_risk_level == "high":
            high_risk += 1

    recent_sessions = (
        db.query(models.InterviewSession)
        .order_by(models.InterviewSession.id.desc())
        .limit(6)
        .all()
    )
    recent = [_session_to_item(s, db) for s in recent_sessions]

    return DashboardStats(
        active_jobs=active_jobs,
        pending_interviews=pending_interviews,
        completed_interviews=completed_interviews,
        high_risk=high_risk,
        recent=recent,
    )
