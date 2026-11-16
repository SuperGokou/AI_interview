"""面试后诚信分析(单一职责:汇集数据 → 计算三类信号 → 落 cheat_events)。

在面试结束后的工作线程里运行,不影响实时语音。每一类信号独立容错:
某个外部服务失败只会少一条信号,不会影响其它信号和评估报告。
"""

import logging
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.answer_review import TextClient, reference_answers, score_turns
from app.core.embeddings import Embedder
from app.core.integrity import CheatSignal
from app.core.integrity_signals import (
    Turn,
    TurnScore,
    TurnSimilarity,
    build_turns,
    latency_signal,
    probe_gap_signal,
    similarity_ratio,
    similarity_signal,
)
from app.db import models

logger = logging.getLogger(__name__)

# Kinds owned by this module; re-running the analysis replaces them.
POST_INTERVIEW_KINDS = ("latency_pattern", "probe_gap", "ai_similarity")

# Each checked answer costs one text-model call and one embedding call.
MAX_SIMILARITY_TURNS = 6


def load_turns(db: Session, session_id: int) -> list[Turn]:
    rows = (
        db.query(models.Transcript.role, models.Transcript.text, models.AnswerMetric.latency_ms)
        .outerjoin(models.AnswerMetric, models.AnswerMetric.transcript_id == models.Transcript.id)
        .filter(models.Transcript.session_id == session_id)
        .order_by(models.Transcript.id)
        .all()
    )
    return build_turns([(role, text, latency) for role, text, latency in rows])


def _questions(db: Session, session_id: int) -> list[dict]:
    sess = db.get(models.InterviewSession, session_id)
    if sess is None:
        return []
    rows = db.query(models.Question).filter_by(job_id=sess.job_id).all()
    return [{"prompt": q.prompt, "is_probe": q.is_probe} for q in rows]


def _similarities(
    client: TextClient, embedder: Embedder, turns: Sequence[Turn], scores: Sequence[TurnScore]
) -> list[TurnSimilarity]:
    small_talk = {s.index for s in scores if s.kind == "other"}
    candidates = [t for t in turns if t.substantive and t.question and t.index not in small_talk]
    longest = sorted(candidates, key=lambda t: -len(t.answer))[:MAX_SIMILARITY_TURNS]
    results: list[TurnSimilarity] = []
    for turn in sorted(longest, key=lambda t: t.index):
        try:
            references = reference_answers(client, turn.question)
            vectors = embedder.embed([turn.answer, *references])
            ratio = similarity_ratio(vectors[0], vectors[1:])
        except Exception:
            logger.exception("AI-similarity check failed for turn %s", turn.index)
            continue
        if ratio is not None:
            results.append(TurnSimilarity(index=turn.index, ratio=ratio))
    return results


def compute_signals(
    turns: Sequence[Turn],
    questions: Sequence[dict],
    *,
    client: TextClient | None,
    embedder: Embedder | None,
) -> list[CheatSignal]:
    signals: list[CheatSignal | None] = [latency_signal(turns)]
    scores: list[TurnScore] = []
    if client is not None and any(t.substantive for t in turns):
        try:
            scores = score_turns(client, turns, questions)
            signals.append(probe_gap_signal(turns, scores))
        except Exception:
            logger.exception("per-answer scoring failed; probe-gap signal skipped")
        if embedder is not None:
            signals.append(
                similarity_signal(turns, _similarities(client, embedder, turns, scores))
            )
    return [s for s in signals if s is not None]


def analyze_integrity(
    db: Session,
    session_id: int,
    *,
    client: TextClient | None,
    embedder: Embedder | None,
) -> list[CheatSignal]:
    """Compute the post-interview signals and replace this session's previous ones."""
    turns = load_turns(db, session_id)
    if not turns:
        return []
    signals = compute_signals(turns, _questions(db, session_id), client=client, embedder=embedder)
    db.query(models.CheatEvent).filter(
        models.CheatEvent.session_id == session_id,
        models.CheatEvent.kind.in_(POST_INTERVIEW_KINDS),
    ).delete(synchronize_session=False)
    db.add_all(
        models.CheatEvent(
            session_id=session_id, kind=s.kind, severity=s.severity, evidence=s.evidence
        )
        for s in signals
    )
    db.commit()
    return signals
