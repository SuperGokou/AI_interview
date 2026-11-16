"""仪表盘统计 REST(单一职责:聚合指标 + 最近会话)。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.integrity import compute_integrity_level
from app.core.session_summary import (
    SessionListItem,
    load_sessions,
    severities_by_session,
    summarize_sessions,
)
from app.db import models
from app.db.base import get_db

router = APIRouter(prefix="/api/dashboard")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class DashboardStats(BaseModel):
    active_jobs: int
    pending_interviews: int
    completed_interviews: int
    high_risk: int
    recent: list[SessionListItem]


# Job statuses that count as "open": the admin UI writes "active"; older data uses "招聘中".
_OPEN_JOB_STATUSES = ("active", "招聘中")
_RECENT_LIMIT = 6


def _count_high_risk(db: Session) -> int:
    """Sessions with a red integrity level or a high-risk report (two queries total)."""
    session_ids = [row[0] for row in db.query(models.InterviewSession.id).all()]
    severities = severities_by_session(db, session_ids)
    flagged = {
        sid for sid, events in severities.items() if compute_integrity_level(events) == "red"
    }
    high_reports = db.query(models.Report.session_id).filter(
        models.Report.ai_risk_level == "high"
    )
    known = set(session_ids)
    flagged.update(row[0] for row in high_reports if row[0] in known)
    return len(flagged)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=DashboardStats)
def get_stats(db: Session = Depends(get_db)):
    active_jobs = (
        db.query(models.Job).filter(models.Job.status.in_(_OPEN_JOB_STATUSES)).count()
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

    high_risk = _count_high_risk(db)
    recent = summarize_sessions(db, load_sessions(db, limit=_RECENT_LIMIT))

    return DashboardStats(
        active_jobs=active_jobs,
        pending_interviews=pending_interviews,
        completed_interviews=completed_interviews,
        high_risk=high_risk,
        recent=recent,
    )
