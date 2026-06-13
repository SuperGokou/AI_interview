from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db import models


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    session = TestSession()
    yield session
    session.close()


def test_job_defaults(db):
    job = models.Job(title="后端工程师", jd="写后端")
    db.add(job)
    db.commit()
    assert job.id is not None
    assert job.language == "zh"
    assert job.interviewer_voice == "Tina"
    assert job.duration_minutes == 30


def test_question_belongs_to_job_with_difficulty(db):
    job = models.Job(title="后端", jd="x")
    db.add(job)
    db.commit()
    q = models.Question(
        job_id=job.id, prompt="什么是索引?", key_points="B+树/加速查询",
        reference_answer="...", difficulty="中级", is_probe=False,
    )
    db.add(q)
    db.commit()
    assert q.id is not None
    assert q.difficulty == "中级"
    assert q.is_probe is False
    assert db.query(models.Question).filter_by(job_id=job.id).count() == 1


def test_session_has_link_token_and_status(db):
    job = models.Job(title="后端", jd="x")
    cand = models.Candidate(name="张三")
    db.add_all([job, cand])
    db.commit()
    s = models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token="tok-123")
    db.add(s)
    db.commit()
    assert s.status == "pending"
    assert s.link_token == "tok-123"


def test_cheat_event_and_report_link_to_session(db):
    job = models.Job(title="后端", jd="x")
    cand = models.Candidate(name="李四")
    db.add_all([job, cand])
    db.commit()
    s = models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token="t2")
    db.add(s)
    db.commit()
    ev = models.CheatEvent(session_id=s.id, kind="gaze_off_screen", severity="medium",
                           evidence="视线偏离 8s", ts=datetime(2026, 6, 13, 10, 0, 0))
    rep = models.Report(session_id=s.id, ai_risk_level="low", overall="建议进入复面")
    db.add_all([ev, rep])
    db.commit()
    assert ev.id is not None and rep.id is not None
    assert db.query(models.CheatEvent).filter_by(session_id=s.id).count() == 1
