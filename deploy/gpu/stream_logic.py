"""Streaming lip-sync bookkeeping: audio buffering, frame readiness, speech gate, wire format.

Pure numpy, no GPU, so it is unit-testable anywhere. Timing model:
  video frame f covers audio [f/FPS, (f+1)/FPS) of its utterance, and the model's
  audio window for that frame reaches LOOKAHEAD_FRAMES further. A frame is therefore
  renderable once that much audio has arrived, or immediately when the utterance ends.
"""
import struct
import threading

import numpy as np

from speech_gate import SpeechGate, frame_is_active

FPS = 25
MODEL_RATE = 16000  # sample rate the audio encoder expects
# The model's window needs 2 frames of future audio; one more keeps the newest
# frame from being rendered against zero-padded audio that is about to arrive.
LOOKAHEAD_FRAMES = 3
MAX_UTTERANCE_SECONDS = 120

_HEADER = struct.Struct("<II")  # utterance id, frame index


def pack_frame(utterance: int, index: int, jpeg: bytes) -> bytes:
    return _HEADER.pack(utterance, index) + jpeg


def unpack_frame(message: bytes) -> tuple[int, int, bytes]:
    utterance, index = _HEADER.unpack_from(message)
    return utterance, index, message[_HEADER.size:]


def resample_to_model_rate(samples: np.ndarray, rate: int) -> np.ndarray:
    """Polyphase resampling of a whole buffer (no per-chunk filter edge artefacts)."""
    if rate == MODEL_RATE:
        return samples
    from math import gcd

    from scipy.signal import resample_poly

    divisor = gcd(MODEL_RATE, rate)
    return resample_poly(samples, MODEL_RATE // divisor, rate // divisor).astype(np.float32)


class UtteranceBuffer:
    """Audio of one interviewer utterance plus how many frames were already rendered."""

    def __init__(self, rate: int):
        if rate not in (16000, 24000, 48000):
            raise ValueError("unsupported sample rate")
        self.rate = rate
        self._chunks: list[np.ndarray] = []
        self._samples = 0
        self.rendered = 0
        self.final = False
        self._gate_state = SpeechGate()
        self._gate: list[float] = []
        # Audio is appended on the event loop while a worker thread renders.
        self._lock = threading.Lock()

    @property
    def seconds(self) -> float:
        return self._samples / self.rate

    @property
    def empty(self) -> bool:
        return self._samples == 0

    def append_pcm16(self, pcm: bytes) -> None:
        if self.final:
            raise ValueError("utterance already ended")
        usable = len(pcm) - len(pcm) % 2
        if not usable:
            return
        chunk = np.frombuffer(pcm[:usable], dtype="<i2").astype(np.float32) / 32768.0
        with self._lock:
            if (self._samples + len(chunk)) / self.rate > MAX_UTTERANCE_SECONDS:
                raise ValueError("utterance too long")
            self._chunks.append(chunk)
            self._samples += len(chunk)

    def end(self) -> None:
        self.final = True

    def audio(self) -> np.ndarray:
        with self._lock:
            return self._audio_locked()

    def _audio_locked(self) -> np.ndarray:
        if len(self._chunks) > 1:
            self._chunks = [np.concatenate(self._chunks)]
        return self._chunks[0] if self._chunks else np.zeros(0, np.float32)

    def snapshot(self, max_frames: int) -> tuple[np.ndarray, range]:
        """Atomically pick the next frames to render and the audio they were
        counted against, so audio arriving mid-render cannot desynchronise them."""
        with self._lock:
            frames = range(self.rendered, self.total_frames())[:max_frames]
            return self._audio_locked(), frames

    def total_frames(self) -> int:
        """Frames this utterance has audio for (final) or can safely render (streaming)."""
        available = int(self.seconds * FPS + 1e-6)
        return available if self.final else max(0, available - LOOKAHEAD_FRAMES)

    def pending(self) -> range:
        return range(self.rendered, self.total_frames())

    def gate_for(self, frames: range, audio: np.ndarray | None = None) -> list[float]:
        """0..1 speech level per frame: opens quickly, eases shut in pauses."""
        if audio is None:
            audio = self.audio()
        per_frame = self.rate / FPS
        while len(self._gate) < frames.stop:
            i = len(self._gate)
            active = frame_is_active(audio, i, per_frame) or frame_is_active(audio, i + 1, per_frame)
            self._gate.append(self._gate_state.step(active))
        return self._gate[frames.start:frames.stop]

    def mark_rendered(self, frames: range) -> None:
        self.rendered = frames.stop

    @property
    def finished(self) -> bool:
        return self.final and self.rendered >= self.total_frames()
