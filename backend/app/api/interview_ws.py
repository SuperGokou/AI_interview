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
from app.core.mouth_stream import MouthStream
from app.core.proctor import ProctorMonitor, ProctorUnavailable, VisionProctor
from app.core.proctor_audio import AudioWindow, pcm_to_wav, worth_hearing
from app.core.silence import SilenceWatch, nudge_text
from app.core.violations import (
    END,
    FAREWELL_SECONDS,
    TERMINATION_KIND,
    ViolationPolicy,
    end_notice,
    ending_text,
    needs_reminder,
    reminder_text,
    warning_text,
)
from app.core.interview_trace import InterviewTrace
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


def _default_proctor():
    """Camera proctoring; None when switched off or no key is configured."""
    settings = get_settings()
    if not settings.proctor_interval_s or not settings.proctor_api_key:
        return None
    return VisionProctor()


proctor_factory = _default_proctor

# 模块级,便于测试注入;返回 None 表示跳过对应的面试后信号。
review_client_factory = _default_review_client
embedder_factory = _default_embedder


async def _default_mouth_stream():
    """Realtime lip-sync session; None when not configured or unavailable."""
    settings = get_settings()
    return await MouthStream.connect(
        settings.mouth_stream_url, settings.mouth_stream_key, settings.output_sample_rate
    )


# 模块级,便于测试注入 fake;返回 None 表示本场面试使用近似口型。
mouth_stream_factory = _default_mouth_stream

# 回答 AI 味置信度阈值,超过才记一次作弊事件。
# 仅凭文字判断照读 AI 稿并不可靠(语音识别后的口头回答本来就通顺),所以门槛定得高,
# 单次命中只算弱信号:要多次命中,或与其他信号叠加,才会把诚信等级拉低。
_AI_TEXT_THRESHOLD = 0.8
_AI_TEXT_STRONG = 0.9


def _ai_text_severity(confidence: float) -> str:
    return "medium" if confidence >= _AI_TEXT_STRONG else "low"

# 首帧后延迟一会儿再让面试官主动开场,给几帧缓冲时间。
_OPENER_DELAY_S = 2.0

# 超过职位时长后再留一点收尾时间,然后服务端强制结束,避免挂着的连接持续消耗实时模型额度。
_OVERTIME_GRACE_S = 5 * 60

# 单帧上行大小上限(base64 字符数);超限帧直接丢弃。
_MAX_AUDIO_B64 = 512 * 1024
_MAX_IMAGE_B64 = 3 * 1024 * 1024
# proctor_audio: 另一路不降噪的麦克风,只给监考听,不送给面试官。
_MAX_FRAME_B64 = {
    "audio": _MAX_AUDIO_B64,
    "proctor_audio": _MAX_AUDIO_B64,
    "image": _MAX_IMAGE_B64,
}

# 面试官刚说过话的这段时间内,录音里可能有它从扬声器传出的声音。
# 两次监考检查之间至少歇这么久,模型应答比检查间隔还慢时也不会连轴打满。
_PROCTOR_MIN_PAUSE_S = 0.5

# 面试官的话音落下后,房间里的余响和回声消除的收敛还要一小会儿。
_ECHO_TAIL_S = 1.5

_INTERVIEWER_ECHO_NOTE = "这段时间面试官(AI)正在说话,录音里它的声音不算其他人。"

_FINISHED_STATUSES = ("done", "completed")

# 断开时等待进行中的 AI 味检测落库的最长时间。
_DETECTION_DRAIN_S = 10.0


def _load_session(db: Session, token: str):
    return db.query(models.InterviewSession).filter_by(link_token=token).first()


async def _reject(ws: WebSocket, message: str) -> None:
    await ws.send_json({"type": "error", "message": message})
    await ws.close()


def _serialize_sends(ws) -> None:
    """Let only one task write to the socket at a time.

    Several tasks send to the page (interviewer audio, lip-sync frames, proctoring
    results, interruptions). The websocket library's flow control cannot have two
    writers waiting at once: when the connection backs up it raises, which used to
    kill the audio pump and leave the interview silent.
    """
    lock = asyncio.Lock()
    raw_send = ws.send

    async def send(message) -> None:
        async with lock:
            await raw_send(message)

    ws.send = send


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
    confidence = float(verdict.get("confidence", 0.0))
    if not verdict.get("is_ai_like") or confidence < _AI_TEXT_THRESHOLD:
        return None
    with Session(bind=bind) as worker_db:
        record_cheat_event(
            worker_db, session_id, kind="ai_text", severity=_ai_text_severity(confidence),
            evidence=verdict.get("reason", ""),
        )
        return integrity_level(worker_db, session_id)


def _without_echo(flags: list[str], *, interviewer_spoke: bool) -> list[str]:
    """While the interviewer is talking its voice comes out of the candidate's
    speakers, and the model cannot reliably tell that from a person in the room
    (seen in a real interview). A second voice is only trusted in a clip the
    interviewer was silent in."""
    return [f for f in flags if not (interviewer_spoke and f == "other_voice")]


def _proctor_frame(
    bind,
    session_id: int,
    proctor,
    monitor: ProctorMonitor,
    jpeg: bytes,
    now: float,
    wav: bytes | None = None,
    note: str = "",
):
    """Worker-thread job: look at one camera frame (and listen to the last few
    seconds around the candidate) and persist confirmed findings.

    Returns (new integrity level, kinds recorded) when something was recorded, else None.
    """
    observation = proctor.check(jpeg, wav, note=note) if wav else proctor.check(jpeg)
    confirmed = monitor.update(_without_echo(observation["flags"], interviewer_spoke=bool(note)), now)
    signals = interpret_visual_observation({"flags": confirmed, "detail": observation["detail"]})
    if not signals:
        return None
    with Session(bind=bind) as worker_db:
        for signal in signals:
            record_cheat_event(
                worker_db, session_id, kind=signal.kind, severity=signal.severity,
                evidence=signal.evidence,
            )
        return integrity_level(worker_db, session_id), [signal.kind for signal in signals]


def _record_termination(bind, session_id: int, warnings: int) -> None:
    with Session(bind=bind) as worker_db:
        record_cheat_event(
            worker_db, session_id, kind=TERMINATION_KIND, severity="high",
            evidence=f"累计 {warnings} 次违规(手机、键盘声或旁人),面试被系统终止。",
        )


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
    _serialize_sends(ws)
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
        vad_silence_ms=settings.vad_silence_ms,
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
    silence = SilenceWatch(
        check_in_s=float(settings.silence_nudge_s or 20),
        move_on_s=float(settings.silence_move_on_s),
    )
    # The page holds audio back a little (lip-sync), so it finishes later than sent.
    playback_margin_s = settings.mouth_playback_delay_ms / 1000 + 0.3
    reply = {"generating": False, "dropping": False}
    trace = InterviewTrace(session_id)
    barge: dict = {"task": None}
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

    # Optional realtime lip-sync. Audio chunks are tagged with (utterance, sample
    # position) so the browser can place each mouth frame on its playback clock.
    mouth = await mouth_stream_factory()
    if mouth is not None:
        await ws.send_json(
            {"type": "mouth_config", "delay_ms": settings.mouth_playback_delay_ms, **mouth.config}
        )
    turn = {"utterance": 0, "samples": 0}
    if not settings.proctor_raw_mic:
        await ws.send_json({"type": "proctor_config", "raw_mic": False})

    state_closed = {"value": False}

    async def relay_mouth_frames():
        try:
            async for frame in mouth.frames():
                await ws.send_bytes(frame)
            if state_closed["value"]:
                return  # the interview itself is over; nobody is left to tell
            # The renderer went away mid-interview (restart, crash, network). Tell
            # the page, or it would keep showing a motionless portrait while the
            # interviewer talks instead of falling back to the audio-driven mouth.
            await ws.send_json({"type": "mouth_off"})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("relaying lip-sync frames failed")

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

    async def barge_in():
        """The candidate keeps talking while the interviewer is: stop and listen,
        as a person would, instead of playing the rest of the reply over them."""
        try:
            await asyncio.sleep(settings.barge_in_hold_ms / 1000)
            await stop_speaking()
        finally:
            barge["task"] = None

    async def stop_speaking():
        """Cut off whatever the interviewer is saying, on the server and in the page."""
        now = clock()
        if not silence.interviewer_speaking(now, margin=playback_margin_s):
            return
        if reply["generating"]:
            reply["dropping"] = True
            await bridge.cancel_response()
            if mouth is not None:
                await mouth.reset()
            if turn["samples"]:
                turn["utterance"] += 1
                turn["samples"] = 0
        silence.cut_short(now)
        logger.info("interview %s: interviewer cut off mid-reply", session_id)
        trace("interviewer_cut_off", was_generating=reply["dropping"])
        await ws.send_json({"type": "interrupt"})

    async def say_now(text: str):
        trace("interviewer_told_to_speak_now", prompt=text[:60])
        """Have the interviewer say something right away rather than after the
        sentence it is in the middle of: a warning that comes 15 s late is useless."""
        await stop_speaking()
        await bridge.trigger_response(text)

    async def pump_downstream():
        try:
            while True:
                event = await bridge.events()
                kind = event.get("kind")
                if kind == "audio":
                    if reply["dropping"]:
                        continue  # the rest of a reply the candidate talked over
                    if not reply["generating"]:
                        trace("interviewer_audio_starts")
                    reply["generating"] = True
                    pcm = event["data"]
                    timer.on_interviewer_audio(len(pcm), clock())
                    silence.interviewer_audio(
                        len(pcm) / 2 / settings.output_sample_rate, clock()
                    )
                    await ws.send_json(
                        {
                            "type": "audio",
                            "data": base64.b64encode(pcm).decode(),
                            "u": turn["utterance"],
                            "p": turn["samples"],
                        }
                    )
                    turn["samples"] += len(pcm) // 2
                    if mouth is not None and mouth.alive:
                        await mouth.send_audio(pcm)
                elif kind == "response_done":
                    trace("response_done", dropped=reply["dropping"])
                    reply["generating"] = reply["dropping"] = False
                    if turn["samples"]:
                        turn["utterance"] += 1
                        turn["samples"] = 0
                    if mouth is not None:
                        await mouth.end_utterance()
                elif kind == "transcript_delta":
                    await ws.send_json({"type": "transcript_delta", "text": event["text"]})
                elif kind == "transcript":
                    trace("interviewer_said", text=event["text"])
                    _persist("interviewer", event["text"])
                    await ws.send_json({"type": "transcript", "text": event["text"]})
                elif kind == "user_transcript":
                    text = event["text"]
                    trace("candidate_said", text=text)
                    _persist(
                        "candidate", text, latency_ms=timer.on_candidate_transcript().latency_ms
                    )
                    silence.candidate_stopped(clock())
                    await ws.send_json({"type": "user_transcript", "text": text})
                    _spawn(check_ai_text(text))
                elif kind == "speech_started":
                    trace(
                        "candidate_speech_started",
                        interviewer_audible=silence.interviewer_speaking(
                            clock(), margin=playback_margin_s
                        ),
                    )
                    timer.on_candidate_speech_started(clock())
                    silence.candidate_started(clock())
                    if (
                        settings.barge_in_hold_ms
                        and barge["task"] is None
                        and silence.interviewer_speaking(clock(), margin=playback_margin_s)
                    ):
                        barge["task"] = _spawn(barge_in())
                elif kind == "speech_stopped":
                    trace("candidate_speech_stopped")
                    silence.candidate_stopped(clock())
                    if barge["task"] is not None:
                        barge["task"].cancel()  # a cough or a word, not an interruption
                        barge["task"] = None
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
            # Without this pump the interviewer is mute. End the interview where the
            # candidate can see it instead of leaving them talking to a silent page.
            try:
                await ws.send_json(
                    {"type": "error", "message": "面试连接出现异常，请刷新页面后重新进入。"}
                )
                await ws.close()
            except Exception:
                pass

    async def proactive_opener():
        try:
            await asyncio.sleep(_OPENER_DELAY_S)
            await bridge.trigger_response(opener_text)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - defensive
            logger.exception("interview proactive opener failed")

    proctor = proctor_factory()
    camera = {"frame": None, "seen": None}
    # Sound for proctoring: the browser's unprocessed microphone when it sends one,
    # otherwise the (noise-suppressed) audio the interviewer hears.
    room_audio = {
        "raw": AudioWindow(), "mic": AudioWindow(), "has_raw": False, "heard_from": clock(),
    }

    def recent_sound() -> tuple[bytes | None, str]:
        raw, mic = room_audio["raw"].take(), room_audio["mic"].take()
        pcm = raw if room_audio["has_raw"] else mic
        if not worth_hearing(pcm):
            room_audio["heard_from"] = clock()
            return None, ""
        # Judged by when the interviewer's audio was *played*, not generated: a reply
        # is produced in a second or two but keeps playing, queued behind earlier
        # speech, long after. Going by generation time let its echo count as a person.
        heard_from = room_audio["heard_from"]
        room_audio["heard_from"] = clock()
        echo = silence.audible_since(heard_from, margin=playback_margin_s + _ECHO_TAIL_S)
        return pcm_to_wav(pcm), _INTERVIEWER_ECHO_NOTE if echo else ""

    async def end_for_violations(warnings: int):
        """Say why, give the interviewer time to finish the sentence, then hang up."""
        await run_in_threadpool(_record_termination, bind, session_id, warnings)
        await say_now(ending_text(job.language))
        await asyncio.sleep(FAREWELL_SECONDS)
        await ws.send_json({"type": "ended", "message": end_notice(job.language)})
        await ws.close()

    async def proctor_loop():
        """Every few seconds, have the vision model look at the newest camera frame."""
        monitor = ProctorMonitor()
        policy = ViolationPolicy(limit=settings.violation_limit)
        interval = float(settings.proctor_interval_s or 20)
        last_start = clock()
        while True:
            # Fixed rhythm: the time a check takes comes out of the wait, so a
            # 3 s interval means a look every 3 s, not every 3 s plus the model's
            # answer time. A check slower than the interval runs back to back.
            await asyncio.sleep(max(_PROCTOR_MIN_PAUSE_S, interval - (clock() - last_start)))
            last_start = clock()
            frame = camera["frame"]
            if frame is None or frame is camera["seen"]:
                continue  # camera off or no new picture since the last look
            camera["seen"] = frame
            wav, note = recent_sound()
            try:
                found = await run_in_threadpool(
                    _proctor_frame, bind, session_id, proctor, monitor, frame, clock(), wav, note
                )
                if found is None:
                    continue
                level, kinds = found
                trace("proctor_found", kinds=kinds)
                await ws.send_json({"type": "integrity", "level": level})
                action = policy.record(kinds)
                if action == END:
                    await end_for_violations(policy.count)
                    return
                if action is not None:
                    await say_now(warning_text(kinds, policy.count, policy.limit, job.language))
                elif needs_reminder(kinds):
                    # Not a violation; said once the interviewer is free.
                    await bridge.trigger_response(reminder_text(job.language))
            except asyncio.CancelledError:
                raise
            except ProctorUnavailable as exc:
                logger.error("camera proctoring switched off for this interview: %s", exc)
                return
            except Exception:
                logger.exception("camera proctoring check failed")

    async def silence_loop():
        """A real interviewer does not wait for ever: check in, then move on."""
        while True:
            await asyncio.sleep(1.0)
            repeated = silence.repeated
            stage = silence.due(clock())
            if stage is None:
                continue
            logger.info("interview %s: breaking the silence (%s)", session_id, stage)
            trace("silence_prompt", stage=stage)
            try:
                await bridge.trigger_response(
                    nudge_text(stage, job.language, repeated=repeated)
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("could not prompt the interviewer to break the silence")

    silence_task = asyncio.create_task(silence_loop()) if settings.silence_nudge_s else None
    proctor_task = asyncio.create_task(proctor_loop()) if proctor is not None else None
    down_task = asyncio.create_task(pump_downstream())
    relay_task = asyncio.create_task(relay_mouth_frames()) if mouth is not None else None
    opener_task: asyncio.Task | None = None
    try:
        async with asyncio.timeout(max_seconds):
            while True:
                frame = _decode_frame(await ws.receive_text())
                if frame is None:
                    continue
                msg_type, payload = frame
                if msg_type == "audio":
                    room_audio["mic"].append(payload)
                    await bridge.send_audio(payload)
                elif msg_type == "proctor_audio":
                    room_audio["has_raw"] = True
                    room_audio["raw"].append(payload)
                else:
                    camera["frame"] = payload
                    await bridge.send_image(payload)
                    if opener_task is None:
                        opener_task = asyncio.create_task(proactive_opener())
    except WebSocketDisconnect:
        pass
    except TimeoutError:
        logger.info("interview %s reached its time limit; closing", session_id)
        try:
            await ws.send_json({"type": "ended", "message": "面试时间已到，本次面试已自动结束。"})
            await ws.close()
        except Exception:  # the peer may already be gone
            pass
    except Exception:  # pragma: no cover - defensive
        logger.exception("interview upstream loop error")
    finally:
        with anyio.CancelScope(shield=True):
            state_closed["value"] = True
            if mouth is not None:
                await mouth.close()  # ends the relay task's frame iterator
            if background:
                # Let an in-flight check on the final answer finish and be recorded.
                await asyncio.wait(background, timeout=_DETECTION_DRAIN_S)
            for task in (
                down_task, opener_task, relay_task, proctor_task, silence_task, *background
            ):
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
