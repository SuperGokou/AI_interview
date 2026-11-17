"""/ws/interview — 候选人面试会话桥接 Qwen-Omni,落库转写并维护会话生命周期。

借鉴 yzbot realtime.py:下行 pump 任务把桥接事件转发给浏览器(并落库转写),
主循环转发上行音视频帧。模块级 bridge_factory 便于测试注入 Fake。
"""

import asyncio
import base64
import binascii
import json
import logging
from datetime import UTC, datetime

import anyio
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.core.answer_timing import TurnTimer
from app.core.cheat_detection import AiTextDetector
from app.core.cheat_store import integrity_level, record_cheat_event
from app.core.deepseek_client import DeepSeekClient
from app.core.embeddings import EmbeddingNotConfigured, OpenAICompatibleEmbedder
from app.core.integrity import interpret_visual_observation
from app.core.integrity_analysis import analyze_integrity
from app.core.interview_bridge import InterviewBridge
from app.core.report_store import build_report
from app.core.scoring import ReportGenerator
from app.db import models
from app.db.base import get_db
from app.prompts.interviewer import build_interviewer_instructions, opener_for

logger = logging.getLogger(__name__)
router = APIRouter()

# 模块级,便于测试 monkeypatch 注入 Fake bridge。
bridge_factory = InterviewBridge

# 模块级,便于测试注入 Fake detector(避免真实 DeepSeek 网络调用)。
ai_detector_factory = AiTextDetector

# 模块级,便于测试 monkeypatch 注入 Fake report generator。
report_generator_factory = ReportGenerator



def _default_review_client():
    """Text model for the post-interview analysis; None when no key is configured."""
    return DeepSeekClient() if get_settings().deepseek_api_key else None


def _default_embedder():
    try:
        return OpenAICompatibleEmbedder()
    except EmbeddingNotConfigured:
        return None


# 模块级,便于测试注入;返回 None 表示跳过对应的面试后信号。
review_client_factory = _default_review_client
embedder_factory = _default_embedder

# 回答 AI 味置信度阈值,超过才记一次作弊事件。
_AI_TEXT_THRESHOLD = 0.6

# 首帧后延迟一会儿再让面试官主动开场,给几帧缓冲时间。
_OPENER_DELAY_S = 2.0

# 超过职位时长后再留一点收尾时间,然后服务端强制结束,避免挂着的连接持续消耗实时模型额度。
_OVERTIME_GRACE_S = 5 * 60

# 单帧上行大小上限(base64 字符数);超限帧直接丢弃。
_MAX_AUDIO_B64 = 512 * 1024
_MAX_IMAGE_B64 = 3 * 1024 * 1024
_MAX_FRAME_B64 = {"audio": _MAX_AUDIO_B64, "image": _MAX_IMAGE_B64}

_FINISHED_STATUSES = ("done", "completed")

# 断开时等待进行中的 AI 味检测落库的最长时间。
_DETECTION_DRAIN_S = 10.0


def _load_session(db: Session, token: str):
    return db.query(models.InterviewSession).filter_by(link_token=token).first()


async def _reject(ws: WebSocket, message: str) -> None:
    await ws.send_json({"type": "error", "message": message})
    await ws.close()


def _decode_frame(raw: str) -> tuple[str, bytes] | None:
    """Parse one upstream frame; None for anything malformed or oversized.

    A single bad frame must not end the interview, so errors are swallowed here.
    """
    try:
        msg = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(msg, dict):
        return None
    msg_type, data = msg.get("type"), msg.get("data")
    limit = _MAX_FRAME_B64.get(msg_type)
    if limit is None or not isinstance(data, str) or not data or len(data) > limit:
        return None
    try:
        return msg_type, base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None


def _detect_ai_text(bind, session_id: int, detector, text: str) -> str | None:
    """Worker-thread job: run the (blocking) detector and persist a hit.

    Returns the new integrity level when an event was recorded, else None.
    """
    verdict = detector.detect(text)
    if not verdict.get("is_ai_like") or verdict.get("confidence", 0.0) < _AI_TEXT_THRESHOLD:
        return None
    with Session(bind=bind) as worker_db:
        record_cheat_event(
            worker_db, session_id, kind="ai_text", severity="high",
            evidence=verdict.get("reason", ""),
        )
        return integrity_level(worker_db, session_id)


def _generate_report(bind, session_id: int) -> None:
    """Worker-thread job: analyse integrity, then score, unless nothing was said."""
    with Session(bind=bind) as report_db:
        has_transcript = (
            report_db.query(models.Transcript.id).filter_by(session_id=session_id).first()
        )
        if has_transcript is None:
            return  # nothing to score; do not spend a model call on an empty interview
        try:
            # Runs first so the report's integrity summary includes these signals.
            analyze_integrity(
                report_db, session_id,
                client=review_client_factory(), embedder=embedder_factory(),
            )
        except Exception:
            report_db.rollback()
            logger.exception("post-interview integrity analysis failed")
        build_report(report_db, session_id, report_generator_factory())


@router.websocket("/ws/interview")
async def interview_ws(ws: WebSocket, db: Session = Depends(get_db)):
    await ws.accept()
    token = ws.query_params.get("token", "")
    sess = _load_session(db, token) if token else None
    if sess is None:
        await _reject(ws, "invalid token")
        return
    if sess.status in _FINISHED_STATUSES:
        # An invite link is single-use: replaying it must not start another paid model session.
        await _reject(ws, "该面试已结束，请联系管理员获取新的面试链接。")
        return

    job = db.get(models.Job, sess.job_id)
    if job is None:
        await _reject(ws, "面试对应的职位已不存在，请联系管理员。")
        return
    settings = get_settings()
    candidate = db.get(models.Candidate, sess.candidate_id)
    questions = db.query(models.Question).filter_by(job_id=job.id).all()
    q_dicts = [
        {
            "prompt": q.prompt,
            "difficulty": q.difficulty,
            "key_points": q.key_points,
            "follow_ups": q.follow_ups,
        }
        for q in questions
    ]
    instructions = build_interviewer_instructions(
        job_title=job.title,
        jd=job.jd,
        questions=q_dicts,
        language=job.language,
        candidate_name=candidate.name if candidate else "",
        duration_minutes=job.duration_minutes,
        interviewer_name=settings.interviewer_name,
        interviewer_company=settings.interviewer_company,
    )

    bridge = bridge_factory(
        model=settings.qwen_model,
        url=settings.qwen_ws_url,
        voice=job.interviewer_voice,
        instructions=instructions,
        api_key=settings.dashscope_api_key,
    )
    try:
        await bridge.connect()
    except Exception:
        # Missing/invalid model key, wrong endpoint, provider outage: tell the
        # candidate instead of dropping the socket, and leave the invite usable.
        logger.exception("realtime model connection failed")
        await _reject(ws, "面试服务暂时不可用，请稍后重试或联系管理员。")
        return

    sess.status = "active"
    sess.started_at = datetime.now(UTC)
    db.commit()
    session_id, bind = sess.id, db.get_bind()
    opener_text = opener_for(
        job.language, name=settings.interviewer_name, company=settings.interviewer_company
    )
    max_seconds = max(1, job.duration_minutes) * 60 + _OVERTIME_GRACE_S

    timer = TurnTimer(sample_rate=settings.output_sample_rate)
    clock = asyncio.get_running_loop().time

    def _persist(role: str, text: str, *, latency_ms: int | None = None) -> None:
        row = models.Transcript(session_id=session_id, role=role, text=text)
        db.add(row)
        if latency_ms is not None:
            db.flush()  # assigns row.id
            db.add(
                models.AnswerMetric(
                    session_id=session_id, transcript_id=row.id, latency_ms=latency_ms
                )
            )
        db.commit()

    detector = ai_detector_factory()
    background: set[asyncio.Task] = set()

    async def check_ai_text(text: str) -> None:
        """Runs beside the pump: a slow or failing detector must never delay or
        stop the interviewer's audio."""
        try:
            level = await run_in_threadpool(_detect_ai_text, bind, session_id, detector, text)
            if level is not None:
                await ws.send_json({"type": "integrity", "level": level})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("AI-text detection failed")

    def _spawn(coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        background.add(task)
        task.add_done_callback(background.discard)
        return task

    async def pump_downstream():
        try:
            while True:
                event = await bridge.events()
                kind = event.get("kind")
                if kind == "audio":
                    timer.on_interviewer_audio(len(event["data"]), clock())
                    await ws.send_json(
                        {"type": "audio", "data": base64.b64encode(event["data"]).decode()}
                    )
                elif kind == "transcript_delta":
                    await ws.send_json({"type": "transcript_delta", "text": event["text"]})
                elif kind == "transcript":
                    _persist("interviewer", event["text"])
                    await ws.send_json({"type": "transcript", "text": event["text"]})
                elif kind == "user_transcript":
                    text = event["text"]
                    _persist(
                        "candidate", text, latency_ms=timer.on_candidate_transcript().latency_ms
                    )
                    await ws.send_json({"type": "user_transcript", "text": text})
                    _spawn(check_ai_text(text))
                elif kind == "speech_started":
                    timer.on_candidate_speech_started(clock())
                elif kind == "vision":
                    # 注:真实 Qwen 视觉观测的产出留待 Phase 6 联调;这里建好处理管线。
                    signals = interpret_visual_observation(
                        {"flags": event.get("flags", []), "detail": event.get("detail", "")}
                    )
                    for s in signals:
                        record_cheat_event(
                            db, session_id, kind=s.kind, severity=s.severity, evidence=s.evidence
                        )
                    if signals:
                        await ws.send_json(
                            {"type": "integrity", "level": integrity_level(db, session_id)}
                        )
                elif kind == "close":
                    await ws.close()
                    break
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - defensive
            logger.exception("interview downstream pump error")

    async def proactive_opener():
        try:
            await asyncio.sleep(_OPENER_DELAY_S)
            await bridge.trigger_response(opener_text)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - defensive
            logger.exception("interview proactive opener failed")

    down_task = asyncio.create_task(pump_downstream())
    opener_task: asyncio.Task | None = None
    try:
        async with asyncio.timeout(max_seconds):
            while True:
                frame = _decode_frame(await ws.receive_text())
                if frame is None:
                    continue
                msg_type, payload = frame
                if msg_type == "audio":
                    await bridge.send_audio(payload)
                else:
                    await bridge.send_image(payload)
                    if opener_task is None:
                        opener_task = asyncio.create_task(proactive_opener())
    except WebSocketDisconnect:
        pass
    except TimeoutError:
        logger.info("interview %s reached its time limit; closing", session_id)
        try:
            await ws.send_json({"type": "error", "message": "面试时间已到，本次面试已自动结束。"})
            await ws.close()
        except Exception:  # the peer may already be gone
            pass
    except Exception:  # pragma: no cover - defensive
        logger.exception("interview upstream loop error")
    finally:
        with anyio.CancelScope(shield=True):
            if background:
                # Let an in-flight check on the final answer finish and be recorded.
                await asyncio.wait(background, timeout=_DETECTION_DRAIN_S)
            for task in (down_task, opener_task, *background):
                if task is not None:
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
            try:
                await bridge.close()
            except Exception:
                logger.exception("closing realtime bridge failed")
            sess.status = "done"
            sess.ended_at = datetime.now(UTC)
            db.commit()
            try:
                # Separate SQLAlchemy session in a worker thread: a slow scoring
                # provider must not block the event loop or another live interview.
                await run_in_threadpool(_generate_report, bind, session_id)
            except Exception:
                logger.exception("auto report generation failed")
