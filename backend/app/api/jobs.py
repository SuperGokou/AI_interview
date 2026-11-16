"""职位 CRUD REST(单一职责:职位增删改查)。"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import QWEN_VOICES
from app.db import models
from app.db.base import get_db

router = APIRouter(prefix="/api/jobs")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class JobIn(BaseModel):
    # Lengths mirror the column sizes: Postgres rejects over-long values with a 500.
    title: str = Field(min_length=1, max_length=128)
    jd: str = Field(max_length=20_000)
    interviewer_voice: str = "Tina"
    language: Literal["zh", "en"] = "zh"
    duration_minutes: int = Field(default=30, ge=1, le=240)
    status: str = Field(default="active", min_length=1, max_length=16)

    @field_validator("interviewer_voice")
    @classmethod
    def _known_voice(cls, value: str) -> str:
        if value not in QWEN_VOICES:
            raise ValueError(f"interviewer_voice must be one of {', '.join(QWEN_VOICES)}")
        return value


class JobOut(BaseModel):
    id: int
    title: str
    jd: str
    interviewer_voice: str
    language: str
    duration_minutes: int
    status: str
    question_count: int
    candidate_count: int

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_job_or_404(job_id: int, db: Session) -> models.Job:
    job = db.get(models.Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


def _counts(db: Session, column, job_ids: list[int]) -> dict[int, int]:
    """Row count per job for the given foreign-key column, in one grouped query."""
    if not job_ids:
        return {}
    rows = db.query(column, func.count()).filter(column.in_(job_ids)).group_by(column).all()
    return {job_id: count for job_id, count in rows}


def _jobs_to_out(jobs: list[models.Job], db: Session) -> list[JobOut]:
    job_ids = [j.id for j in jobs]
    question_counts = _counts(db, models.Question.job_id, job_ids)
    candidate_counts = _counts(db, models.InterviewSession.job_id, job_ids)
    return [
        JobOut(
            id=job.id,
            title=job.title,
            jd=job.jd,
            interviewer_voice=job.interviewer_voice,
            language=job.language,
            duration_minutes=job.duration_minutes,
            status=job.status,
            question_count=question_counts.get(job.id, 0),
            candidate_count=candidate_counts.get(job.id, 0),
        )
        for job in jobs
    ]


def _job_to_out(job: models.Job, db: Session) -> JobOut:
    return _jobs_to_out([job], db)[0]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(models.Job).order_by(models.Job.id).all()
    return _jobs_to_out(jobs, db)


@router.post("", response_model=JobOut)
def create_job(body: JobIn, db: Session = Depends(get_db)):
    job = models.Job(
        title=body.title,
        jd=body.jd,
        interviewer_voice=body.interviewer_voice,
        language=body.language,
        duration_minutes=body.duration_minutes,
        status=body.status,
    )
    db.add(job)
    db.commit()
    return _job_to_out(job, db)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = _get_job_or_404(job_id, db)
    return _job_to_out(job, db)


@router.put("/{job_id}", response_model=JobOut)
def update_job(job_id: int, body: JobIn, db: Session = Depends(get_db)):
    job = _get_job_or_404(job_id, db)
    job.title = body.title
    job.jd = body.jd
    job.interviewer_voice = body.interviewer_voice
    job.language = body.language
    job.duration_minutes = body.duration_minutes
    job.status = body.status
    db.commit()
    return _job_to_out(job, db)


@router.delete("/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = _get_job_or_404(job_id, db)
    if db.query(models.InterviewSession).filter_by(job_id=job.id).count():
        # Sessions, transcripts and reports reference the job; deleting it would orphan them.
        raise HTTPException(
            status_code=409,
            detail="该职位已有面试记录，无法删除；可将状态改为“已关闭”。",
        )
    # Delete related questions first (cascade-safe)
    db.query(models.Question).filter_by(job_id=job.id).delete()
    db.delete(job)
    db.commit()
    return {"ok": True}
