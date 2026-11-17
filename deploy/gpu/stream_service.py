"""Private streaming lip-sync endpoint. Bind only to loopback; reach it through a tunnel.

WebSocket /stream?rate=24000   (Authorization: Bearer <GPU_API_KEY>)
  client -> server  binary: PCM16 mono audio of the interviewer's speech
                    text:   {"type":"end"}    the utterance is complete, flush its last frames
                            {"type":"reset"}  drop the current utterance (interruption)
  server -> client  text:   {"type":"ready", fps, frame, patch}
                            {"type":"done", "utterance": n, "frames": k}
                    binary: frame = <u32 utterance><u32 frame index><JPEG of the patch>
"""
import asyncio
import json
import logging
import os
import secrets

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from stream_logic import UtteranceBuffer, pack_frame

logger = logging.getLogger("kunyao.mouth")

# Render as soon as this many frames are ready; fewer only when the utterance ends.
MIN_BATCH_FRAMES = 3
MAX_CHUNK_BYTES = 512 * 1024


def create_app(engine, api_key: str, max_sessions: int = 4) -> FastAPI:
    if not api_key:
        raise ValueError("A private GPU_API_KEY is required")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    sessions = {"active": 0}

    @app.get("/health")
    def health():
        return {"ready": True, "sessions": sessions["active"], "max_sessions": max_sessions}

    @app.websocket("/stream")
    async def stream(ws: WebSocket):
        supplied = ws.headers.get("authorization", "")
        if not secrets.compare_digest(supplied, f"Bearer {api_key}"):
            await ws.close(code=4401)
            return
        try:
            rate = int(ws.query_params.get("rate", "24000"))
            UtteranceBuffer(rate)
        except ValueError:
            await ws.close(code=4400)
            return
        if sessions["active"] >= max_sessions:
            await ws.close(code=4429)  # busy: the caller falls back to audio-driven mouth
            return
        sessions["active"] += 1
        await ws.accept()
        try:
            await ws.send_text(json.dumps({"type": "ready", **engine.describe()}))
            await _serve(ws, engine, rate)
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("stream session failed")
        finally:
            sessions["active"] -= 1

    return app


async def _serve(ws: WebSocket, engine, rate: int) -> None:
    state = {"utterance": 0, "buffer": UtteranceBuffer(rate), "closed": False}
    wake = asyncio.Event()

    async def render_loop():
        while True:
            await wake.wait()
            wake.clear()
            while True:
                utterance, buffer = state["utterance"], state["buffer"]
                ready = len(buffer.pending())
                if ready == 0 or (ready < MIN_BATCH_FRAMES and not buffer.final):
                    break
                frames = await run_in_threadpool(engine.render, buffer)
                if state["utterance"] != utterance:
                    break  # reset while rendering: these frames are stale
                for index, jpeg in frames:
                    await ws.send_bytes(pack_frame(utterance, index, jpeg))
            utterance, buffer = state["utterance"], state["buffer"]
            if buffer.finished and not buffer.empty:
                await ws.send_text(json.dumps(
                    {"type": "done", "utterance": utterance, "frames": buffer.rendered}))
                _next_utterance(state, rate)

    async def receive_loop():
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            data = message.get("bytes")
            if data is not None:
                if len(data) > MAX_CHUNK_BYTES:
                    continue
                if state["buffer"].final:  # audio after "end" belongs to the next utterance
                    await _drain(state, wake)
                try:
                    state["buffer"].append_pcm16(data)
                except ValueError:
                    _next_utterance(state, rate)  # over-long utterance: start over
                wake.set()
                continue
            kind = _message_type(message.get("text"))
            if kind == "end":
                if state["buffer"].empty:
                    continue  # nothing was said: there is no utterance to finish
                state["buffer"].end()
                wake.set()
            elif kind == "reset":
                _next_utterance(state, rate)

    # Whichever side stops first ends the session: the peer leaving, or a render
    # failure. A failed renderer must never leave the caller waiting for frames.
    renderer = asyncio.create_task(render_loop())
    receiver = asyncio.create_task(receive_loop())
    try:
        await asyncio.wait({renderer, receiver}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        state["closed"] = True
        for task in (renderer, receiver):
            task.cancel()
        results = await asyncio.gather(renderer, receiver, return_exceptions=True)
    failure = next(
        (r for r in results if isinstance(r, Exception) and not isinstance(r, WebSocketDisconnect)),
        None,
    )
    if failure is not None:
        logger.error("stream session failed", exc_info=failure)
        await ws.close(code=1011)


async def _drain(state, wake: asyncio.Event) -> None:
    """Let the render loop finish the ended utterance before new audio starts the next."""
    ended = state["utterance"]
    wake.set()
    while state["utterance"] == ended and not state["closed"]:
        await asyncio.sleep(0.005)


def _next_utterance(state, rate: int) -> None:
    state["utterance"] += 1
    state["buffer"] = UtteranceBuffer(rate)


def _message_type(text):
    try:
        payload = json.loads(text or "")
    except ValueError:
        return None
    return payload.get("type") if isinstance(payload, dict) else None


if __name__ == "__main__":
    import uvicorn

    from stream_engine import StreamEngine

    logging.basicConfig(level=logging.INFO)
    application = create_app(
        StreamEngine(), os.environ["GPU_API_KEY"], int(os.environ.get("MAX_SESSIONS", "4"))
    )
    uvicorn.run(application, host="127.0.0.1", port=int(os.environ.get("PORT", "8765")), workers=1)
