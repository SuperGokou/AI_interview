"""开发辅助端点 — POST /api/dev/demo-session。

在无需完整报名流程的情况下快速创建一个演示面试会话并返回 token,
供本地开发和 E2E 测试使用。绝对不可在生产环境开启(通过 DEV_ENDPOINTS
环境变量控制)。
"""

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.tokens import generate_link_token
from app.db import models
from app.db.base import get_db

router = APIRouter(prefix="/api/dev")

_DEMO_JOB_TITLE = "演示职位 · 后端工程师"
_DEMO_JD = (
    "负责公司核心后端服务的设计、开发和维护，"
    "熟悉 Python/Go/Java 之一，了解 RESTful API 设计，"
    "具备数据库调优和分布式系统基础知识。"
)
_DEMO_CANDIDATE_NAME = "演示候选人"


def _ensure_demo_job(db: Session) -> models.Job:
    """幂等地确保演示 Job 及其题库存在，返回该 Job。"""
    settings = get_settings()
    job = db.query(models.Job).filter_by(title=_DEMO_JOB_TITLE).first()
    if job is None:
        job = models.Job(
            title=_DEMO_JOB_TITLE,
            jd=_DEMO_JD,
            language="zh",
            interviewer_voice=settings.qwen_voice,
            duration_minutes=30,
        )
        db.add(job)
        db.flush()

        questions = [
            models.Question(
                job_id=job.id,
                prompt="请简单介绍一下你自己以及你最近参与的项目。",
                difficulty="初级",
                is_probe=False,
            ),
            models.Question(
                job_id=job.id,
                prompt="请解释数据库索引的原理，以及什么情况下会导致索引失效？",
                difficulty="中级",
                is_probe=False,
            ),
            models.Question(
                job_id=job.id,
                prompt="在分布式系统中，你会如何保证接口的幂等性？",
                difficulty="高级",
                is_probe=True,
            ),
        ]
        db.add_all(questions)
        db.commit()
        db.refresh(job)
    return job


@router.post("/demo-session")
def create_demo_session(db: Session = Depends(get_db)):
    """创建演示会话并返回 {token}。

    仅在 DEV_ENDPOINTS=true 时可用（默认开启，以便本地开发）。
    """
    if os.getenv("DEV_ENDPOINTS", "true").lower() not in ("1", "true", "yes"):
        raise HTTPException(status_code=404, detail="not found")

    job = _ensure_demo_job(db)
    candidate = models.Candidate(name=_DEMO_CANDIDATE_NAME)
    db.add(candidate)
    db.flush()
    sess = models.InterviewSession(
        job_id=job.id,
        candidate_id=candidate.id,
        link_token=generate_link_token(),
    )
    db.add(sess)
    db.commit()
    return {"token": sess.link_token}
