"""Realtime lip-sync relay: the stream client and its wiring into the interview websocket."""

import asyncio
import base64
import json
import struct

import pytest
import websockets

from app.core.mouth_stream import MouthStream
from app.db import models

READY = {"type": "ready", "fps": 25, "frame": {"width": 1672, "height": 941},
         "patch": {"x": 763, "y": 281, "width": 215, "height": 142}}


def frame(utterance, index, body=b"jpeg"):
    return struct.pack("<II", utterance, index) + body


# --- client against a real local websocket server ---------------------------


async def _serve(handler):
    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, f"ws://127.0.0.1:{port}/stream"


async def test_client_sends_audio_and_receives_frames():
    received = []

    async def handler(ws):
        assert ws.request.headers["Authorization"] == "Bearer key"
        assert ws.request.path == "/stream?rate=24000"
        await ws.send(json.dumps(READY))
        async for message in ws:
            received.append(message)
            if isinstance(message, str):
                await ws.send(frame(0, 0))
                await ws.send(json.dumps({"type": "done", "utterance": 0, "frames": 1}))
                await ws.send(b"x")  # too short to be a frame: ignored
                await ws.close()

    server, url = await _serve(handler)
    try:
        stream = await MouthStream.connect(url, "key", 24000)
        assert stream.config["patch"]["width"] == 215 and "type" not in stream.config
        assert await stream.end_utterance() is False  # nothing sent yet
        await stream.send_audio(b"\x01\x02")
        assert await stream.end_utterance() is True
        frames = [f async for f in stream.frames()]
        assert frames == [frame(0, 0)]
        assert received == [b"\x01\x02", json.dumps({"type": "end"})]
        assert stream.alive is False  # the service closed: quietly disabled
        await stream.send_audio(b"\x00\x00")  # no-op, must not raise
    finally:
        server.close()
        await server.wait_closed()


async def test_client_returns_none_when_unconfigured_unreachable_or_refused():
    assert await MouthStream.connect("", "key", 24000) is None
    assert await MouthStream.connect("ws://127.0.0.1:9/stream", "key", 24000) is None

    async def busy(ws):
        await ws.close(code=4429)

    server, url = await _serve(busy)
    try:
        assert await MouthStream.connect(url, "key", 24000) is None
    finally:
        server.close()
        await server.wait_closed()


# --- interview websocket wiring ---------------------------------------------


class _Mouth:
    """Stands in for MouthStream: records calls, emits one frame per utterance end."""

    def __init__(self, *, fail_audio=False):
        self.config = {k: v for k, v in READY.items() if k != "type"}
        self.alive = True
        self.audio, self.ends, self.closed = [], 0, False
        self._queue: asyncio.Queue = asyncio.Queue()
        self._fail_audio = fail_audio

    async def send_audio(self, pcm):
        if self._fail_audio:
            self.alive = False
            return
        self.audio.append(pcm)

    async def end_utterance(self):
        self.ends += 1
        await self._queue.put(frame(self.ends - 1, 0))
        return True

    async def frames(self):
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item

    async def close(self):
        self.closed = True
        await self._queue.put(None)


class _Bridge:
    events_to_emit: list[dict] = []

    def __init__(self, **_kwargs):
        self._pending = list(type(self).events_to_emit)

    async def connect(self): pass

    async def events(self):
        if self._pending:
            return self._pending.pop(0)
        await asyncio.Event().wait()

    async def trigger_response(self, instructions=""): pass
    async def send_audio(self, pcm): pass
    async def send_image(self, jpeg): pass
    async def close(self): pass


def _seed(db, token):
    job = models.Job(title="后端", jd="x", interviewer_voice="Tina")
    cand = models.Candidate(name="张三")
    db.add_all([job, cand])
    db.commit()
    db.add(models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token=token))
    db.commit()


@pytest.fixture
def wired(client, db_session, monkeypatch):
    def start(mouth, events, token="tok-mouth"):
        _seed(db_session, token)
        _Bridge.events_to_emit = events

        async def factory():
            return mouth

        monkeypatch.setattr("app.api.interview_ws.bridge_factory", _Bridge)
        monkeypatch.setattr("app.api.interview_ws.ai_detector_factory", lambda: object())
        monkeypatch.setattr("app.api.interview_ws.mouth_stream_factory", factory)
        return client.websocket_connect(f"/ws/interview?token={token}")

    return start


def test_audio_is_tagged_and_frames_are_relayed(wired):
    mouth = _Mouth()
    events = [
        {"kind": "audio", "data": b"\x00\x00" * 100},
        {"kind": "audio", "data": b"\x00\x00" * 50},
        {"kind": "response_done"},
        {"kind": "audio", "data": b"\x00\x00" * 10},
        {"kind": "response_done"},
        {"kind": "response_done"},  # a reply with no audio must not advance the utterance
        {"kind": "audio", "data": b"\x00\x00" * 10},
    ]
    with wired(mouth, events) as ws:
        config = ws.receive_json()
        assert config["type"] == "mouth_config"
        assert config["patch"] == READY["patch"] and config["delay_ms"] > 0
        audio, frames = [], []
        while len(audio) < 4 or len(frames) < 2:
            message = ws.receive()
            if message.get("bytes") is not None:
                frames.append(struct.unpack_from("<II", message["bytes"]))
            else:
                payload = json.loads(message["text"])
                if payload["type"] == "audio":
                    audio.append((payload["u"], payload["p"], len(base64.b64decode(payload["data"]))))
    assert audio == [(0, 0, 200), (0, 100, 100), (1, 0, 20), (2, 0, 20)]
    assert frames[:2] == [(0, 0), (1, 0)]
    assert mouth.audio[0] == b"\x00\x00" * 100 and len(mouth.audio) == 4
    assert mouth.closed is True


def test_interview_continues_when_the_lip_sync_stream_dies(wired):
    mouth = _Mouth(fail_audio=True)
    events = [
        {"kind": "audio", "data": b"\x00\x00" * 10},
        {"kind": "transcript", "text": "下一个问题"},
        {"kind": "audio", "data": b"\x00\x00" * 10},
    ]
    with wired(mouth, events, token="tok-mouth-dead") as ws:
        assert ws.receive_json()["type"] == "mouth_config"
        types = [ws.receive_json()["type"] for _ in range(3)]
    assert types == ["audio", "transcript", "audio"]
    assert mouth.audio == []


def test_without_a_lip_sync_service_audio_is_still_tagged(client, db_session, monkeypatch):
    _seed(db_session, "tok-no-mouth")
    _Bridge.events_to_emit = [{"kind": "audio", "data": b"\x00\x00" * 10}]
    monkeypatch.setattr("app.api.interview_ws.bridge_factory", _Bridge)
    monkeypatch.setattr("app.api.interview_ws.ai_detector_factory", lambda: object())
    with client.websocket_connect("/ws/interview?token=tok-no-mouth") as ws:
        first = ws.receive_json()
    assert first["type"] == "audio" and first["u"] == 0 and first["p"] == 0


def test_bridge_emits_response_done():
    from app.core.interview_bridge import InterviewBridge

    bridge = InterviewBridge(model="m", url="u", voice="Tina", instructions="i")
    emitted = []
    bridge._emit = emitted.append
    bridge._handle_event({"type": "response.audio_transcript.delta", "delta": "你好"})
    bridge._handle_event({"type": "response.done"})
    assert emitted == [
        {"kind": "transcript_delta", "text": "你好"},
        {"kind": "transcript", "text": "你好"},
        {"kind": "response_done"},
    ]


@pytest.mark.parametrize(
    "value, expected", [(None, 450), ("700", 700), ("99999", 2000), ("-5", 0), ("abc", 450)]
)
def test_playback_delay_setting_is_bounded(monkeypatch, value, expected):
    from app.config import _bounded_int

    if value is None:
        monkeypatch.delenv("MOUTH_PLAYBACK_DELAY_MS", raising=False)
    else:
        monkeypatch.setenv("MOUTH_PLAYBACK_DELAY_MS", value)
    assert _bounded_int("MOUTH_PLAYBACK_DELAY_MS", 450, 0, 2000) == expected
