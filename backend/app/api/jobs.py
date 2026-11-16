"""职位 CRUD REST(单一职责:职位增删改查)。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import models
from app.db.base import get_db

router = APIRouter(prefix="/api/jobs")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class JobIn(BaseModel):
    title: str
    jd: str
    interviewer_voice: str = "Tina"
    language: str = "zh"
    duration_minutes: int = 30
    status: str = "招聘中"


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


def _job_to_out(job: models.Job, db: Session) -> JobOut:
    question_count = (
        db.query(models.Question).filter_by(job_id=job.id).count()
    )
    candidate_count = (
        db.query(models.InterviewSession).filter_by(job_id=job.id).count()
    )
    return JobOut(
        id=job.id,
        title=job.title,
        jd=job.jd,
        interviewer_voice=job.interviewer_voice,
        language=job.language,
        duration_minutes=job.duration_minutes,
        status=job.status,
        question_count=question_count,
        candidate_count=candidate_count,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(models.Job).order_by(models.Job.id).all()
    return [_job_to_out(j, db) for j in jobs]


@router.post("", response_model=JobOut)
def create_job(body: JobIn, db: Session = Depends(get_db)):
    # TODO: HR auth
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
    # TODO: HR auth
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
    # TODO: HR auth
    job = _get_job_or_404(job_id, db)
    # Delete related questions first (cascade-safe)
    db.query(models.Question).filter_by(job_id=job.id).delete()
    db.delete(job)
    db.commit()
    return {"ok": True}
