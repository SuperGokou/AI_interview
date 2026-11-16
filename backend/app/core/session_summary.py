"""会话列表聚合(单一职责:用固定条数的查询构建会话摘要,避免逐行 N+1)。"""

from collections.abc import Iterable, Sequence

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.integrity import compute_integrity_level
from app.db import models

_SCORE_FIELDS = ("score_professional", "score_communication", "score_job_match")


class SessionListItem(BaseModel):
    token: str
    candidate_name: str
    job_title: str
    status: str
    integrity_level: str
    score_overall: int | None
    created_at: str | None


def overall_score(report: models.Report | None) -> int | None:
    """Mean of the scored dimensions; None until a report exists."""
    if report is None:
        return None
    scores = [v for v in (getattr(report, f) for f in _SCORE_FIELDS) if v is not None]
    return round(sum(scores) / len(scores)) if scores else None


def severities_by_session(db: Session, session_ids: Iterable[int]) -> dict[int, list[dict]]:
    """One query for every cheat event of the given sessions."""
    ids = list(session_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(models.CheatEvent.session_id, models.CheatEvent.severity).where(
            models.CheatEvent.session_id.in_(ids)
        )
    ).all()
    grouped: dict[int, list[dict]] = {}
    for session_id, severity in rows:
        grouped.setdefault(session_id, []).append({"severity": severity})
    return grouped


def load_sessions(db: Session, *, limit: int | None = None) -> list[models.InterviewSession]:
    """Newest first, with job / candidate / report eagerly joined."""
    query = (
        db.query(models.InterviewSession)
        .options(
            joinedload(models.InterviewSession.job),
            joinedload(models.InterviewSession.candidate),
            joinedload(models.InterviewSession.report),
        )
        .order_by(models.InterviewSession.id.desc())
    )
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def summarize_sessions(
    db: Session, sessions: Sequence[models.InterviewSession]
) -> list[SessionListItem]:
    severities = severities_by_session(db, (s.id for s in sessions))
    items: list[SessionListItem] = []
    for sess in sessions:
        raw_ts = sess.started_at or sess.consented_at
        items.append(
            SessionListItem(
                token=sess.link_token,
                candidate_name=sess.candidate.name if sess.candidate else "",
                job_title=sess.job.title if sess.job else "",
                status=sess.status,
                integrity_level=compute_integrity_level(severities.get(sess.id, [])),
                score_overall=overall_score(sess.report),
                created_at=raw_ts.isoformat() if raw_ts else None,
            )
        )
    return items
