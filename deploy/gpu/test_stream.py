"""Streaming lip-sync: buffering/readiness logic and the WebSocket protocol (fake engine)."""
import json
import unittest

import numpy as np
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from stream_logic import (
    FPS, LOOKAHEAD_FRAMES, UtteranceBuffer, pack_frame, resample_to_model_rate, unpack_frame,
)
from stream_service import create_app

RATE = 24000


def pcm(seconds, amplitude=0.1, rate=RATE):
    return (np.full(int(seconds * rate), amplitude * 32767, "<i2")).tobytes()


class BufferTests(unittest.TestCase):
    def test_frames_wait_for_lookahead_until_the_utterance_ends(self):
        buffer = UtteranceBuffer(RATE)
        buffer.append_pcm16(pcm(0.1))
        self.assertEqual(len(buffer.pending()), 0)  # 2.5 frames of audio, 3 needed ahead
        buffer.append_pcm16(pcm(0.3))
        self.assertEqual(buffer.pending(), range(0, 10 - LOOKAHEAD_FRAMES))
        buffer.mark_rendered(buffer.pending())
        self.assertFalse(buffer.finished)
        buffer.end()
        self.assertEqual(buffer.pending(), range(7, 10))
        buffer.mark_rendered(buffer.pending())
        self.assertTrue(buffer.finished)

    def test_audio_is_normalised_and_odd_bytes_ignored(self):
        buffer = UtteranceBuffer(RATE)
        buffer.append_pcm16(np.array([32767, -32768], "<i2").tobytes() + b"\x01")
        np.testing.assert_allclose(buffer.audio(), [32767 / 32768, -1.0], atol=1e-6)

    def test_rejects_audio_after_end_and_over_long_utterances(self):
        buffer = UtteranceBuffer(16000)
        buffer.end()
        with self.assertRaises(ValueError):
            buffer.append_pcm16(pcm(0.1, rate=16000))
        long = UtteranceBuffer(16000)
        with self.assertRaises(ValueError):
            long.append_pcm16(b"\x00\x00" * (16000 * 121))
        with self.assertRaises(ValueError):
            UtteranceBuffer(44100)

    def test_gate_is_stable_across_incremental_calls(self):
        whole = UtteranceBuffer(RATE)
        whole.append_pcm16(pcm(0.4, 0.0) + pcm(0.8, 0.1))
        whole.end()
        expected = whole.gate_for(range(0, 30))
        parts = UtteranceBuffer(RATE)
        parts.append_pcm16(pcm(0.4, 0.0) + pcm(0.8, 0.1))
        parts.end()
        got = parts.gate_for(range(0, 12)) + parts.gate_for(range(12, 30))
        np.testing.assert_allclose(got, expected)
        self.assertEqual(expected[0], 0)
        self.assertGreater(expected[-1], 0.99)

    def test_snapshot_is_consistent_while_audio_keeps_arriving(self):
        import threading

        buffer = UtteranceBuffer(RATE)
        stop = threading.Event()

        def feed():
            while not stop.is_set():
                try:
                    buffer.append_pcm16(pcm(0.01))
                except ValueError:
                    return

        feeder = threading.Thread(target=feed)
        feeder.start()
        try:
            for _ in range(300):
                audio, frames = buffer.snapshot(8)
                # Every selected frame, plus its lookahead, is backed by real audio.
                needed = (frames.stop + LOOKAHEAD_FRAMES) * RATE // FPS if len(frames) else 0
                self.assertGreaterEqual(len(audio), needed)
                buffer.mark_rendered(frames)
        finally:
            stop.set()
            feeder.join()
        self.assertEqual(len(buffer.audio()), buffer._samples)  # no chunk was dropped

    def test_resampling_keeps_duration(self):
        audio = np.sin(np.linspace(0, 200, RATE, dtype=np.float32))
        self.assertEqual(len(resample_to_model_rate(audio, RATE)), 16000)
        self.assertIs(resample_to_model_rate(audio, 16000), audio)

    def test_frame_wire_format_round_trips(self):
        self.assertEqual(unpack_frame(pack_frame(7, 123, b"jpeg")), (7, 123, b"jpeg"))


class BrokenEngine:
    def describe(self):
        return FakeEngine().describe()

    def render(self, buffer):
        raise RuntimeError("GPU fault")


class FakeEngine:
    def describe(self):
        return {"fps": FPS, "frame": {"width": 1672, "height": 941},
                "patch": {"x": 1, "y": 2, "width": 3, "height": 4}}

    def render(self, buffer):
        frames = buffer.pending()
        buffer.mark_rendered(frames)
        return [(i, b"f%d" % i) for i in frames]


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(FakeEngine(), "secret", max_sessions=1))
        self.auth = {"Authorization": "Bearer secret"}

    def collect(self, ws):
        """Read until the utterance's done message; returns (frames, done)."""
        frames = []
        while True:
            message = ws.receive()
            if message.get("bytes") is not None:
                frames.append(unpack_frame(message["bytes"]))
            else:
                payload = json.loads(message["text"])
                if payload["type"] == "done":
                    return frames, payload

    def test_requires_the_key(self):
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/stream", headers={"Authorization": "Bearer nope"}):
                pass
        self.assertEqual(ctx.exception.code, 4401)

    def test_rejects_unsupported_sample_rate(self):
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/stream?rate=44100", headers=self.auth):
                pass
        self.assertEqual(ctx.exception.code, 4400)

    def test_streams_every_frame_once_in_order_across_utterances(self):
        with self.client.websocket_connect("/stream?rate=24000", headers=self.auth) as ws:
            ready = json.loads(ws.receive_text())
            self.assertEqual(ready["type"], "ready")
            self.assertEqual(ready["patch"]["width"], 3)
            for chunk in range(5):  # 1 s in 200 ms chunks
                ws.send_bytes(pcm(0.2))
            ws.send_text(json.dumps({"type": "end"}))
            frames, done = self.collect(ws)
            self.assertEqual([(u, i) for u, i, _ in frames], [(0, i) for i in range(25)])
            self.assertEqual(done, {"type": "done", "utterance": 0, "frames": 25})
            ws.send_bytes(pcm(0.4))  # next utterance starts with the next audio
            ws.send_text(json.dumps({"type": "end"}))
            frames, done = self.collect(ws)
            self.assertEqual([(u, i) for u, i, _ in frames], [(1, i) for i in range(10)])

    def test_reset_starts_a_new_utterance_and_bad_messages_are_ignored(self):
        with self.client.websocket_connect("/stream", headers=self.auth) as ws:
            ws.receive_text()
            ws.send_bytes(pcm(0.08))  # too short to render anything yet
            ws.send_text("not json")
            ws.send_text(json.dumps({"type": "reset"}))
            ws.send_bytes(pcm(0.2))
            ws.send_text(json.dumps({"type": "end"}))
            frames, done = self.collect(ws)
            self.assertEqual(done["utterance"], 1)
            self.assertEqual(len(frames), 5)

    def test_render_failure_closes_the_session_instead_of_hanging(self):
        client = TestClient(create_app(BrokenEngine(), "secret"))
        with client.websocket_connect("/stream", headers=self.auth) as ws:
            ws.receive_text()
            ws.send_bytes(pcm(0.5))
            closed = ws.receive()
            self.assertEqual(closed["type"], "websocket.close")
            self.assertEqual(closed["code"], 1011)
        self.assertEqual(client.get("/health").json()["sessions"], 0)

    def test_refuses_sessions_beyond_capacity(self):
        with self.client.websocket_connect("/stream", headers=self.auth) as first:
            first.receive_text()
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self.client.websocket_connect("/stream", headers=self.auth):
                    pass
            self.assertEqual(ctx.exception.code, 4429)
        self.assertEqual(self.client.get("/health").json()["sessions"], 0)


if __name__ == "__main__":
    unittest.main()
