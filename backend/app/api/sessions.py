"""面试会话 REST(单一职责:会话创建/查询/同意条款)。"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.cheat_store import events_with_snapshot, get_snapshot, list_cheat_events
from app.core.integrity import compute_integrity_level
from app.core.report_store import build_report
from app.core.scoring import ReportGenerator
from app.core.session_summary import SessionListItem, load_sessions, summarize_sessions
from app.core.tokens import generate_link_token
from app.db import models
from app.db.base import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions")

# 模块级,便于测试注入 fake generator(避免真实 DeepSeek 调用)。
report_generator_factory = ReportGenerator


class CreateSessionRequest(BaseModel):
    job_id: int
    candidate_name: str = Field(min_length=1, max_length=64)


class CreateSessionResponse(BaseModel):
    token: str
    status: str


class JobSummary(BaseModel):
    title: str
    language: str
    duration_minutes: int
    interviewer_voice: str


class SessionInfo(BaseModel):
    token: str
    status: str
    candidate_name: str
    consented: bool
    job: JobSummary


class ReportOut(BaseModel):
    score_professional: int | None
    score_communication: int | None
    score_job_match: int | None
    score_demeanor: int | None
    ai_risk_level: str | None
    feedback: str | None
    overall: str | None


def _get_session_or_404(token: str, db: Session) -> models.InterviewSession:
    sess = db.query(models.InterviewSession).filter_by(link_token=token).first()
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    return sess


@router.get("", response_model=list[SessionListItem])
def list_sessions(db: Session = Depends(get_db)):
    """列出所有面试会话(最新优先),用于 HR 后台记录列表、仪表盘等。"""
    return summarize_sessions(db, load_sessions(db))


@router.post("", response_model=CreateSessionResponse)
def create_session(req: CreateSessionRequest, db: Session = Depends(get_db)):
    job = db.get(models.Job, req.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    name = req.candidate_name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="candidate_name must not be blank")
    candidate = models.Candidate(name=name)
    db.add(candidate)
    db.flush()
    sess = models.InterviewSession(
        job_id=job.id, candidate_id=candidate.id, link_token=generate_link_token()
    )
    db.add(sess)
    db.commit()
    return CreateSessionResponse(token=sess.link_token, status=sess.status)


@router.get("/{token}", response_model=SessionInfo)
def get_session(token: str, db: Session = Depends(get_db)):
    sess = _get_session_or_404(token, db)
    job = db.get(models.Job, sess.job_id)
    if job is None:  # legacy data: the job was removed while the invite still exists
        raise HTTPException(status_code=404, detail="session not found")
    candidate = db.get(models.Candidate, sess.candidate_id)
    return SessionInfo(
        token=token,
        status=sess.status,
        candidate_name=candidate.name if candidate else "",
        consented=sess.consented_at is not None,
        job=JobSummary(
            title=job.title,
            language=job.language,
            duration_minutes=job.duration_minutes,
            interviewer_voice=job.interviewer_voice,
        ),
    )


@router.post("/{token}/consent")
def consent(token: str, db: Session = Depends(get_db)):
    sess = _get_session_or_404(token, db)
    if sess.consented_at is None:  # keep the first consent timestamp as the record
        sess.consented_at = datetime.now(UTC)
        db.commit()
    return {"ok": True, "consented": True}


@router.get("/{token}/cheat/{event_id}/snapshot")
def get_cheat_snapshot(token: str, event_id: int, db: Session = Depends(get_db)):
    """The camera frame a proctoring finding was based on. Admin only: the path is
    not on the public list in app.security."""
    sess = _get_session_or_404(token, db)
    jpeg = get_snapshot(db, sess.id, event_id)
    if jpeg is None:
        raise HTTPException(status_code=404, detail="snapshot not found")
    return Response(content=jpeg, media_type="image/jpeg")


@router.get("/{token}/cheat")
def get_cheat(token: str, db: Session = Depends(get_db)):
    sess = _get_session_or_404(token, db)
    events = list_cheat_events(db, sess.id)
    pictured = events_with_snapshot(db, sess.id)
    return {
        "integrity_level": compute_integrity_level(events),
        "events": [
            {
                "id": e.id,
                "snapshot": e.id in pictured,
                "kind": e.kind,
                "severity": e.severity,
                "evidence": e.evidence,
                "ts": e.ts.isoformat() if e.ts else None,
            }
            for e in events
        ],
    }


def _report_to_out(r: models.Report) -> ReportOut:
    return ReportOut(
        score_professional=r.score_professional,
        score_communication=r.score_communication,
        score_job_match=r.score_job_match,
        score_demeanor=r.score_demeanor,
        ai_risk_level=r.ai_risk_level,
        feedback=r.feedback,
        overall=r.overall,
    )


class TranscriptOut(BaseModel):
    role: str
    text: str
    ts: str | None


@router.get("/{token}/transcripts", response_model=list[TranscriptOut])
def list_transcripts(token: str, db: Session = Depends(get_db)):
    """返回会话的完整对话转写列表(按 id 升序)。"""
    sess = _get_session_or_404(token, db)
    rows = (
        db.query(models.Transcript)
        .filter_by(session_id=sess.id)
        .order_by(models.Transcript.id)
        .all()
    )
    return [
        TranscriptOut(
            role=t.role,
            text=t.text,
            ts=t.ts.isoformat() if t.ts else None,
        )
        for t in rows
    ]


@router.post("/{token}/report", response_model=ReportOut)
def create_report(token: str, db: Session = Depends(get_db)):
    sess = _get_session_or_404(token, db)
    try:
        report = build_report(db, sess.id, report_generator_factory())
    except ValueError as exc:  # the model answered, but not with a usable report
        raise HTTPException(status_code=502, detail="报告生成失败，请重试。") from exc
    except Exception as exc:  # bad key, quota, network: the model could not be reached
        db.rollback()
        logger.exception("report generation failed")
        raise HTTPException(
            status_code=502, detail="评估模型调用失败，请检查评估模型的密钥和额度后重试。"
        ) from exc
    return _report_to_out(report)


@router.get("/{token}/report", response_model=ReportOut)
def get_report(token: str, db: Session = Depends(get_db)):
    sess = _get_session_or_404(token, db)
    report = db.query(models.Report).filter_by(session_id=sess.id).first()
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return _report_to_out(report)
