"""报告聚合与落库(单一职责:从 session 聚合转写/题库/作弊 → 生成 → 落 reports)。"""

from sqlalchemy.orm import Session

from app.core.integrity import compute_integrity_level
from app.core.cheat_store import list_cheat_events
from app.core.scoring import ReportGenerator
from app.db import models


def _cheat_summary(events) -> str:
    if not events:
        return "无作弊信号,诚信:green"
    level = compute_integrity_level(events)
    counts: dict[str, int] = {}
    for e in events:
        counts[e.kind] = counts.get(e.kind, 0) + 1
    parts = ", ".join(f"{k}×{v}" for k, v in counts.items())
    return f"诚信:{level};事件:{parts}"


def build_report(db: Session, session_id: int, generator: ReportGenerator) -> models.Report:
    """聚合 session 数据,调用 generator 评分,写入(或更新)Report 行。"""
    sess = db.get(models.InterviewSession, session_id)
    if sess is None:
        raise ValueError(f"InterviewSession {session_id} not found")
    job = db.get(models.Job, sess.job_id)
    transcripts = (
        db.query(models.Transcript)
        .filter_by(session_id=session_id)
        .order_by(models.Transcript.id)
        .all()
    )
    questions = db.query(models.Question).filter_by(job_id=job.id).all()
    events = list_cheat_events(db, session_id)

    result = generator.generate(
        job_title=job.title,
        jd=job.jd,
        transcripts=[{"role": t.role, "text": t.text} for t in transcripts],
        questions=[
            {
                "prompt": q.prompt,
                "key_points": q.key_points,
                "reference_answer": q.reference_answer,
                "difficulty": q.difficulty,
            }
            for q in questions
        ],
        cheat_summary=_cheat_summary(events),
    )

    report = db.query(models.Report).filter_by(session_id=session_id).first()
    if report is None:
        report = models.Report(session_id=session_id)
        db.add(report)
    report.score_professional = result["score_professional"]
    report.score_communication = result["score_communication"]
    report.score_job_match = result["score_job_match"]
    report.score_demeanor = result["score_demeanor"]
    report.ai_risk_level = result["ai_risk_level"]
    report.feedback = result["feedback"]
    report.overall = result["overall"]
    db.commit()
    return report
