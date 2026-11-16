"""题库 CRUD REST(单一职责:面试题增删改查)。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import models
from app.db.base import get_db

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class QuestionIn(BaseModel):
    prompt: str
    key_points: str | None = None
    reference_answer: str | None = None
    difficulty: str = "中级"
    is_probe: bool = False


class QuestionOut(BaseModel):
    id: int
    job_id: int
    prompt: str
    key_points: str | None
    reference_answer: str | None
    difficulty: str
    is_probe: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_job_or_404(job_id: int, db: Session) -> models.Job:
    job = db.get(models.Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


def _get_question_or_404(question_id: int, db: Session) -> models.Question:
    q = db.get(models.Question, question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="question not found")
    return q


def _question_to_out(q: models.Question) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        job_id=q.job_id,
        prompt=q.prompt,
        key_points=q.key_points,
        reference_answer=q.reference_answer,
        difficulty=q.difficulty,
        is_probe=q.is_probe,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}/questions", response_model=list[QuestionOut])
def list_questions(job_id: int, db: Session = Depends(get_db)):
    _get_job_or_404(job_id, db)
    questions = (
        db.query(models.Question)
        .filter_by(job_id=job_id)
        .order_by(models.Question.id)
        .all()
    )
    return [_question_to_out(q) for q in questions]


@router.post("/jobs/{job_id}/questions", response_model=QuestionOut)
def create_question(
    job_id: int, body: QuestionIn, db: Session = Depends(get_db)
):
    # TODO: HR auth
    _get_job_or_404(job_id, db)
    q = models.Question(
        job_id=job_id,
        prompt=body.prompt,
        key_points=body.key_points,
        reference_answer=body.reference_answer,
        difficulty=body.difficulty,
        is_probe=body.is_probe,
    )
    db.add(q)
    db.commit()
    return _question_to_out(q)


@router.put("/questions/{question_id}", response_model=QuestionOut)
def update_question(
    question_id: int, body: QuestionIn, db: Session = Depends(get_db)
):
    # TODO: HR auth
    q = _get_question_or_404(question_id, db)
    q.prompt = body.prompt
    q.key_points = body.key_points
    q.reference_answer = body.reference_answer
    q.difficulty = body.difficulty
    q.is_probe = body.is_probe
    db.commit()
    return _question_to_out(q)


@router.delete("/questions/{question_id}")
def delete_question(question_id: int, db: Session = Depends(get_db)):
    # TODO: HR auth
    q = _get_question_or_404(question_id, db)
    db.delete(q)
    db.commit()
    return {"ok": True}
