"""Streaming Ditto: window/gate bookkeeping and the WebSocket protocol (fake engine)."""
import json
import struct
import threading
import unittest

import numpy as np
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ditto_logic import LEAD_IN, STEP, TAIL_SECONDS, WINDOW, AudioWindows, patch_rect
from ditto_service import create_app


def pcm(seconds, amplitude=0.1, rate=24000):
    return (np.full(int(seconds * rate), amplitude * 32767, "<i2")).tobytes()


class AudioWindowTests(unittest.TestCase):
    def test_windows_step_through_the_padded_16k_stream(self):
        audio = AudioWindows(24000)
        audio.append_pcm16(pcm(1.0))
        windows = audio.ready_windows()
        available = LEAD_IN + 16000
        self.assertEqual(len(windows), (available - WINDOW) // STEP + 1)
        self.assertTrue(all(len(w) == WINDOW for w in windows))
        self.assertTrue(np.all(windows[0][:LEAD_IN] == 0))  # left context starts silent
        self.assertEqual(audio.ready_windows(), [])  # nothing new until more audio arrives

    def test_end_appends_a_silent_tail_and_flushes_everything(self):
        audio = AudioWindows(16000)
        audio.append_pcm16(pcm(0.3, rate=16000))
        first = len(audio.ready_windows())
        audio.end()
        rest = audio.ready_windows()
        total = LEAD_IN + int(0.3 * 16000) + int(TAIL_SECONDS * 16000)
        self.assertEqual(first + len(rest), -(-total // STEP))
        self.assertTrue(np.all(rest[-1][-100:] == 0))
        with self.assertRaises(ValueError):
            audio.append_pcm16(pcm(0.1))

    def test_resampling_keeps_duration_and_rejects_bad_input(self):
        audio = AudioWindows(48000)
        audio.append_pcm16(pcm(0.5, rate=48000) + b"\x01")  # odd trailing byte is ignored
        self.assertEqual(len(audio.padded_audio), LEAD_IN + 8000)
        with self.assertRaises(ValueError):
            AudioWindows(44100)
        long = AudioWindows(16000)
        with self.assertRaises(ValueError):
            long.append_pcm16(b"\x00\x00" * (16000 * 121))

    def test_patch_rect_is_clamped_and_even(self):
        self.assertEqual(patch_rect((10, 20, 211, 321), (1672, 940)), (6, 16, 208, 308))
        self.assertEqual(patch_rect((0, 0, 1672, 940), (1672, 940)), (0, 0, 1672, 940))


class FakeEngine:
    """Renders 5 frames per audio chunk, after a small delay, from a worker thread."""

    def __init__(self, fail_on=None):
        self.calls, self.fail_on = [], fail_on

    def describe(self):
        return {"fps": 25, "frame": {"width": 1672, "height": 940},
                "patch": {"x": 600, "y": 40, "width": 520, "height": 600}}

    def start(self, on_frame, rate=24000):
        self.calls.append(("start", rate))
        self.on_frame, self.index = on_frame, 0

    def feed(self, data):
        self.calls.append(("feed", len(data)))
        if self.fail_on == "feed":
            raise RuntimeError("GPU fault")
        for _ in range(5):
            self.on_frame(self.index, b"\xff\xd8jpeg")
            self.index += 1

    def finish(self):
        self.calls.append(("finish",))
        self.on_frame(self.index, b"\xff\xd8tail")

    def abort(self):
        self.calls.append(("abort",))


class ServiceTests(unittest.TestCase):
    auth = {"Authorization": "Bearer secret"}

    def collect(self, ws):
        frames = []
        while True:
            message = ws.receive()
            if message.get("bytes") is not None:
                frames.append(struct.unpack_from("<II", message["bytes"]))
            elif json.loads(message["text"])["type"] == "done":
                return frames, json.loads(message["text"])

    def test_auth_rate_and_capacity(self):
        client = TestClient(create_app(FakeEngine(), "secret"))
        for headers, path, code in (({"Authorization": "Bearer no"}, "/stream", 4401),
                                    (self.auth, "/stream?rate=44100", 4400)):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with client.websocket_connect(path, headers=headers):
                    pass
            self.assertEqual(ctx.exception.code, code)
        with client.websocket_connect("/stream", headers=self.auth) as first:
            first.receive_text()
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with client.websocket_connect("/stream", headers=self.auth):
                    pass
            self.assertEqual(ctx.exception.code, 4429)
        self.assertEqual(client.get("/health").json()["sessions"], 0)

    def test_utterances_are_numbered_and_frames_arrive_in_order(self):
        engine = FakeEngine()
        client = TestClient(create_app(engine, "secret"))
        with client.websocket_connect("/stream?rate=24000", headers=self.auth) as ws:
            ready = json.loads(ws.receive_text())
            self.assertEqual(ready["patch"]["width"], 520)
            ws.send_bytes(pcm(0.2))
            ws.send_bytes(pcm(0.2))
            ws.send_text(json.dumps({"type": "end"}))
            frames, done = self.collect(ws)
            self.assertEqual(frames, [(0, i) for i in range(11)])
            self.assertEqual(done["utterance"], 0)
            ws.send_text(json.dumps({"type": "end"}))  # end with no audio is ignored
            ws.send_bytes(pcm(0.2))
            ws.send_text(json.dumps({"type": "end"}))
            frames, done = self.collect(ws)
            self.assertEqual(frames, [(1, i) for i in range(6)])
        self.assertEqual([c[0] for c in engine.calls].count("start"), 2)

    def test_reset_aborts_and_the_next_audio_starts_a_new_utterance(self):
        engine = FakeEngine()
        client = TestClient(create_app(engine, "secret"))
        with client.websocket_connect("/stream", headers=self.auth) as ws:
            ws.receive_text()
            ws.send_bytes(pcm(0.2))
            for _ in range(5):
                ws.receive_bytes()
            ws.send_text(json.dumps({"type": "reset"}))
            ws.send_bytes(pcm(0.2))
            ws.send_text(json.dumps({"type": "end"}))
            frames, done = self.collect(ws)
            self.assertEqual(done["utterance"], 1)
            self.assertEqual({u for u, _ in frames}, {1})
        self.assertIn(("abort",), engine.calls)

    def test_engine_failure_ends_the_session(self):
        client = TestClient(create_app(FakeEngine(fail_on="feed"), "secret"))
        with client.websocket_connect("/stream", headers=self.auth) as ws:
            ws.receive_text()
            ws.send_bytes(pcm(0.2))
            ws.send_bytes(pcm(0.2))
            message = ws.receive()
            while message["type"] != "websocket.close":
                message = ws.receive()
            self.assertEqual(message["code"], 1011)
        self.assertEqual(client.get("/health").json()["sessions"], 0)


if __name__ == "__main__":
    unittest.main()
