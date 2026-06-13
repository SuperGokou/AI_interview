"""ORM 模型(单一职责:表结构)。对应 spec 第 8 节数据模型。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):  # HR / 管理员
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="HR")
    # TODO: 迁移到时区感知 datetime.now(UTC) + DateTime(timezone=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    contact: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    jd: Mapped[str] = mapped_column(Text)
    interviewer_voice: Mapped[str] = mapped_column(String(16), default="Tina")
    language: Mapped[str] = mapped_column(String(8), default="zh")          # zh / en
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    questions: Mapped[list["Question"]] = relationship(back_populates="job")


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    prompt: Mapped[str] = mapped_column(Text)              # 题干
    key_points: Mapped[str | None] = mapped_column(Text, nullable=True)        # 考点
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)  # 标答
    difficulty: Mapped[str] = mapped_column(String(16), default="中级")          # 初级/中级/高级
    is_probe: Mapped[bool] = mapped_column(Boolean, default=False)             # 是否防作弊探针题
    job: Mapped["Job"] = relationship(back_populates="questions")


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    link_token: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/active/done
    consented_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    job: Mapped["Job"] = relationship("Job")
    candidate: Mapped["Candidate"] = relationship("Candidate")
    transcripts: Mapped[list["Transcript"]] = relationship("Transcript")
    recordings: Mapped[list["Recording"]] = relationship("Recording")
    cheat_events: Mapped[list["CheatEvent"]] = relationship("CheatEvent")
    report: Mapped["Report | None"] = relationship("Report", uselist=False)


class Transcript(Base):
    __tablename__ = "transcripts"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"))
    role: Mapped[str] = mapped_column(String(16))  # interviewer / candidate
    text: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Recording(Base):
    __tablename__ = "recordings"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"))
    media_ref: Mapped[str] = mapped_column(String(255))  # 文件路径/对象存储 key
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CheatEvent(Base):
    __tablename__ = "cheat_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"))
    kind: Mapped[str] = mapped_column(String(32))     # gaze_off_screen / multi_person / ai_text ...
    severity: Mapped[str] = mapped_column(String(8))  # low / medium / high
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"), unique=True)
    score_professional: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_communication: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_job_match: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_demeanor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_risk_level: Mapped[str | None] = mapped_column(String(8), nullable=True)  # low/medium/high
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    overall: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
