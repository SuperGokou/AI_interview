"""/ws/interview — 候选人面试会话桥接 Qwen-Omni,落库转写并维护会话生命周期。

借鉴 yzbot realtime.py:下行 pump 任务把桥接事件转发给浏览器(并落库转写),
主循环转发上行音视频帧。模块级 bridge_factory 便于测试注入 Fake。
"""

import asyncio
import base64
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.interview_bridge import InterviewBridge
from app.db import models
from app.db.base import get_db
from app.prompts.interviewer import build_interviewer_instructions, opener_for

logger = logging.getLogger(__name__)
router = APIRouter()

# 模块级,便于测试 monkeypatch 注入 Fake bridge。
bridge_factory = InterviewBridge

# 首帧后延迟一会儿再让面试官主动开场,给几帧缓冲时间。
_OPENER_DELAY_S = 2.0


def _load_session(db: Session, token: str):
    return db.query(models.InterviewSession).filter_by(link_token=token).first()


@router.websocket("/ws/interview")
async def interview_ws(ws: WebSocket, db: Session = Depends(get_db)):
    await ws.accept()
    token = ws.query_params.get("token", "")
    sess = _load_session(db, token) if token else None
    if sess is None:
        await ws.send_json({"type": "error", "message": "invalid token"})
        await ws.close()
        return

    job = db.get(models.Job, sess.job_id)
    candidate = db.get(models.Candidate, sess.candidate_id)
    questions = db.query(models.Question).filter_by(job_id=job.id).all()
    q_dicts = [{"prompt": q.prompt, "difficulty": q.difficulty} for q in questions]
    instructions = build_interviewer_instructions(
        job_title=job.title,
        jd=job.jd,
        questions=q_dicts,
        language=job.language,
        candidate_name=candidate.name if candidate else "",
        duration_minutes=job.duration_minutes,
    )

    settings = get_settings()
    bridge = bridge_factory(
        model=settings.qwen_model,
        url=settings.qwen_ws_url,
        voice=job.interviewer_voice,
        instructions=instructions,
        api_key=settings.dashscope_api_key,
    )
    await bridge.connect()

    sess.status = "active"
    sess.started_at = datetime.utcnow()
    db.commit()

    def _persist(role: str, text: str) -> None:
        db.add(models.Transcript(session_id=sess.id, role=role, text=text))
        db.commit()

    async def pump_downstream():
        try:
            while True:
                event = await bridge.events()
                kind = event.get("kind")
                if kind == "audio":
                    await ws.send_json(
                        {"type": "audio", "data": base64.b64encode(event["data"]).decode()}
                    )
                elif kind == "transcript":
                    _persist("interviewer", event["text"])
                    await ws.send_json({"type": "transcript", "text": event["text"]})
                elif kind == "user_transcript":
                    _persist("candidate", event["text"])
                    await ws.send_json({"type": "user_transcript", "text": event["text"]})
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
            await bridge.trigger_response(opener_for(job.language))
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - defensive
            logger.exception("interview proactive opener failed")

    down_task = asyncio.create_task(pump_downstream())
    opener_task: asyncio.Task | None = None
    try:
        while True:
            msg = await ws.receive_json()
            msg_type = msg.get("type")
            data = msg.get("data")
            if not data:
                continue
            if msg_type == "audio":
                await bridge.send_audio(base64.b64decode(data))
            elif msg_type == "image":
                await bridge.send_image(base64.b64decode(data))
                if opener_task is None:
                    opener_task = asyncio.create_task(proactive_opener())
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - defensive
        logger.exception("interview upstream loop error")
    finally:
        for task in (down_task, opener_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        await bridge.close()
        sess.status = "done"
        sess.ended_at = datetime.utcnow()
        db.commit()
