"""面试会话 REST(单一职责:会话创建/查询/同意条款)。"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.cheat_store import list_cheat_events
from app.core.integrity import compute_integrity_level
from app.core.report_store import build_report
from app.core.scoring import ReportGenerator
from app.core.tokens import generate_link_token
from app.db import models
from app.db.base import get_db

router = APIRouter(prefix="/api/sessions")

# 模块级,便于测试注入 fake generator(避免真实 DeepSeek 调用)。
report_generator_factory = ReportGenerator


class CreateSessionRequest(BaseModel):
    job_id: int
    candidate_name: str


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


@router.post("", response_model=CreateSessionResponse)
def create_session(req: CreateSessionRequest, db: Session = Depends(get_db)):
    job = db.get(models.Job, req.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    candidate = models.Candidate(name=req.candidate_name)
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
    sess.consented_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "consented": True}


@router.get("/{token}/cheat")
def get_cheat(token: str, db: Session = Depends(get_db)):
    sess = _get_session_or_404(token, db)
    events = list_cheat_events(db, sess.id)
    return {
        "integrity_level": compute_integrity_level(events),
        "events": [
            {
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


@router.post("/{token}/report", response_model=ReportOut)
def create_report(token: str, db: Session = Depends(get_db)):
    sess = _get_session_or_404(token, db)
    report = build_report(db, sess.id, report_generator_factory())
    return _report_to_out(report)


@router.get("/{token}/report", response_model=ReportOut)
def get_report(token: str, db: Session = Depends(get_db)):
    sess = _get_session_or_404(token, db)
    report = db.query(models.Report).filter_by(session_id=sess.id).first()
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return _report_to_out(report)
