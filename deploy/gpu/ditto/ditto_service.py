"""Private streaming Ditto endpoint. Same wire protocol as ../stream_service.py, so the
interview backend talks to either without changes. Bind only to loopback.

WebSocket /stream?rate=24000   (Authorization: Bearer <GPU_API_KEY>)
  client -> server  binary: PCM16 mono audio of the interviewer's speech
                    text:   {"type":"end"}    the utterance is complete
                            {"type":"reset"}  drop the current utterance
  server -> client  text:   {"type":"ready", fps, frame, patch}
                            {"type":"done", "utterance": n, "frames": k}
                    binary: <u32 utterance><u32 frame index><JPEG of the patch>
One GPU renders one interview at a time (about 26 fps against 25 needed), so a
second session is refused with 4429 and that interview uses the audio-driven mouth.
"""
import asyncio
import json
import logging
import os
import secrets
import struct
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger("kunyao.ditto")
_HEADER = struct.Struct("<II")
MAX_CHUNK_BYTES = 512 * 1024
SUPPORTED_RATES = (16000, 24000, 48000)


def create_app(engine, api_key: str) -> FastAPI:
    if not api_key:
        raise ValueError("A private GPU_API_KEY is required")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    state = {"busy": False}
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ditto")  # one GPU pipeline

    @app.get("/health")
    def health():
        return {"ready": True, "sessions": int(state["busy"]), "max_sessions": 1}

    @app.websocket("/stream")
    async def stream(ws: WebSocket):
        if not secrets.compare_digest(ws.headers.get("authorization", ""), f"Bearer {api_key}"):
            await ws.close(code=4401)
            return
        try:
            rate = int(ws.query_params.get("rate", "24000"))
        except ValueError:
            rate = -1
        if rate not in SUPPORTED_RATES:
            await ws.close(code=4400)
            return
        if state["busy"]:
            await ws.close(code=4429)
            return
        state["busy"] = True
        await ws.accept()
        try:
            await ws.send_text(json.dumps({"type": "ready", **engine.describe()}))
            await _Session(ws, engine, rate, executor).run()
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("ditto session failed")
            try:  # tell the caller, so it falls back instead of waiting for frames
                await ws.close(code=1011)
            except Exception:
                pass
        finally:
            state["busy"] = False

    return app


class _Session:
    def __init__(self, ws, engine, rate, executor):
        self.ws, self.engine, self.rate, self.executor = ws, engine, rate, executor
        self.loop = asyncio.get_running_loop()
        self.outbox: asyncio.Queue = asyncio.Queue()
        self.utterance = 0
        self.open = False  # an utterance is being rendered
        self.pending = []  # engine calls in flight, in order

    def _call(self, fn, *args):
        future = self.loop.run_in_executor(self.executor, fn, *args)
        self.pending.append(future)
        future.add_done_callback(self._settled)
        return future

    def _settled(self, future):
        """Runs on the event loop as each engine call finishes; a failure is queued
        for the sender so the session ends even if no further message arrives."""
        if future in self.pending:
            self.pending.remove(future)
        if not future.cancelled() and future.exception() is not None:
            self.outbox.put_nowait(future.exception())

    def _on_frame(self, utterance):
        def deliver(index, jpeg):
            self.loop.call_soon_threadsafe(self.outbox.put_nowait, _HEADER.pack(utterance, index) + jpeg)
        return deliver

    def _begin(self):
        self.open = True
        self._call(self.engine.start, self._on_frame(self.utterance), self.rate)

    def _finish(self):
        utterance = self.utterance
        self.open = False
        self.utterance += 1

        def finish_and_report():
            self.engine.finish()
            self.loop.call_soon_threadsafe(
                self.outbox.put_nowait, json.dumps({"type": "done", "utterance": utterance}))
        self._call(finish_and_report)

    async def _sender(self):
        while True:
            item = await self.outbox.get()
            if isinstance(item, BaseException):
                raise item
            if isinstance(item, bytes):
                await self.ws.send_bytes(item)
            else:
                await self.ws.send_text(item)

    async def _receiver(self):
        while True:
            message = await self.ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            data = message.get("bytes")
            if data is not None:
                if not data or len(data) > MAX_CHUNK_BYTES:
                    continue
                if not self.open:
                    self._begin()
                self._call(self.engine.feed, data)
            else:
                kind = _message_type(message.get("text"))
                if kind == "end" and self.open:
                    self._finish()
                elif kind == "reset" and self.open:
                    self.open = False
                    self.utterance += 1
                    self._call(self.engine.abort)

    async def run(self):
        sender = asyncio.create_task(self._sender())
        receiver = asyncio.create_task(self._receiver())
        try:
            done, _ = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            if self.open:
                self._call(self.engine.abort)
            for task in (sender, receiver):
                task.cancel()
            await asyncio.gather(sender, receiver, return_exceptions=True)
            await asyncio.gather(*self.pending, return_exceptions=True)


def _message_type(text):
    try:
        payload = json.loads(text or "")
    except ValueError:
        return None
    return payload.get("type") if isinstance(payload, dict) else None


if __name__ == "__main__":
    import uvicorn

    from ditto_engine import DittoEngine

    logging.basicConfig(level=logging.INFO)
    app = create_app(DittoEngine(), os.environ["GPU_API_KEY"])
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8765")), workers=1)
