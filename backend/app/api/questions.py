"""题库 CRUD REST(单一职责:面试题增删改查)。"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deepseek_client import DeepSeekClient
from app.core.question_generator import MAX_GENERATED, generate_questions
from app.db import models
from app.db.base import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# Drafting several questions with answers takes longer than a scoring call.
_GENERATION_TIMEOUT_S = 120.0


def _default_generator_client():
    """Text model for drafting questions; None when no key is configured."""
    if not get_settings().deepseek_api_key:
        return None
    return DeepSeekClient(timeout=_GENERATION_TIMEOUT_S)


# 模块级,便于测试注入 fake client。
generator_client_factory = _default_generator_client


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class QuestionIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=4_000)
    key_points: str | None = Field(default=None, max_length=4_000)
    reference_answer: str | None = Field(default=None, max_length=8_000)
    difficulty: str = Field(default="中级", min_length=1, max_length=16)
    is_probe: bool = False
    follow_ups: str | None = Field(default=None, max_length=4_000)  # one per line


class GenerateIn(BaseModel):
    count: int = Field(default=5, ge=1, le=MAX_GENERATED)
    focus: str = Field(default="", max_length=200)


class QuestionOut(BaseModel):
    id: int
    job_id: int
    prompt: str
    key_points: str | None
    reference_answer: str | None
    difficulty: str
    is_probe: bool
    follow_ups: str | None = None

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
        follow_ups=q.follow_ups,
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
    _get_job_or_404(job_id, db)
    q = models.Question(
        job_id=job_id,
        prompt=body.prompt,
        key_points=body.key_points,
        reference_answer=body.reference_answer,
        difficulty=body.difficulty,
        is_probe=body.is_probe,
        follow_ups=body.follow_ups,
    )
    db.add(q)
    db.commit()
    return _question_to_out(q)


@router.post("/jobs/{job_id}/questions/generate", response_model=list[QuestionOut])
def generate_job_questions(job_id: int, body: GenerateIn, db: Session = Depends(get_db)):
    """Draft questions from the job description and add them to the bank for review."""
    job = _get_job_or_404(job_id, db)
    client = generator_client_factory()
    if client is None:
        raise HTTPException(status_code=503, detail="未配置 DEEPSEEK_API_KEY，无法生成题目。")
    existing = [q.prompt for q in db.query(models.Question).filter_by(job_id=job_id)]
    try:
        drafts = generate_questions(
            client, job_title=job.title, jd=job.jd, language=job.language,
            count=body.count, existing=existing, focus=body.focus,
        )
    except Exception as exc:
        logger.exception("question generation failed")
        raise HTTPException(status_code=502, detail="题目生成失败，请稍后重试。") from exc
    rows = [
        models.Question(
            job_id=job_id,
            prompt=d.prompt,
            key_points=d.key_points or None,
            reference_answer=d.reference_answer or None,
            difficulty=d.difficulty,
            follow_ups="\n".join(d.follow_ups) or None,
        )
        for d in drafts
    ]
    db.add_all(rows)
    db.commit()
    return [_question_to_out(q) for q in rows]


@router.put("/questions/{question_id}", response_model=QuestionOut)
def update_question(
    question_id: int, body: QuestionIn, db: Session = Depends(get_db)
):
    q = _get_question_or_404(question_id, db)
    q.prompt = body.prompt
    q.key_points = body.key_points
    q.reference_answer = body.reference_answer
    q.difficulty = body.difficulty
    q.is_probe = body.is_probe
    q.follow_ups = body.follow_ups
    db.commit()
    return _question_to_out(q)


@router.delete("/questions/{question_id}")
def delete_question(question_id: int, db: Session = Depends(get_db)):
    q = _get_question_or_404(question_id, db)
    db.delete(q)
    db.commit()
    return {"ok": True}
