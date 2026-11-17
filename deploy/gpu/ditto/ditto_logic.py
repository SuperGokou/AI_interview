"""Pure bookkeeping for streaming Ditto: audio windows, speech gate, frame patch.

No GPU and no Ditto imports, so it is unit-testable anywhere.

Ditto's online mode consumes 16 kHz audio in overlapping windows: each call gets
`WINDOW` samples and the next one starts `STEP` samples later (chunksize (3, 5, 2):
3 frames of left context, 5 new frames, 2 frames of lookahead, 640 samples a frame).
"""
from math import gcd

import numpy as np

MODEL_RATE = 16000
FPS = 25
SAMPLES_PER_FRAME = MODEL_RATE // FPS  # 640
CHUNKSIZE = (3, 5, 2)
LEAD_IN = CHUNKSIZE[0] * SAMPLES_PER_FRAME  # zeros fed before the first window
STEP = CHUNKSIZE[1] * SAMPLES_PER_FRAME  # 3200 samples = 0.2 s
WINDOW = sum(CHUNKSIZE) * SAMPLES_PER_FRAME + 80  # 6480 samples
# Silence appended when an utterance ends, long enough for the speech gate to ease
# the face fully back to the portrait before the overlay hands over to the still image.
TAIL_SECONDS = 1.2
MAX_UTTERANCE_SECONDS = 120


def to_model_rate(samples: np.ndarray, rate: int) -> np.ndarray:
    if rate == MODEL_RATE:
        return samples.astype(np.float32, copy=False)
    from scipy.signal import resample_poly

    divisor = gcd(MODEL_RATE, rate)
    return resample_poly(samples, MODEL_RATE // divisor, rate // divisor).astype(np.float32)


class AudioWindows:
    """Turns incoming PCM16 at any supported rate into Ditto's 16 kHz windows."""

    def __init__(self, rate: int):
        if rate not in (16000, 24000, 48000):
            raise ValueError("unsupported sample rate")
        self.rate = rate
        self._raw: list[np.ndarray] = []
        self._raw_samples = 0
        self._next = 0  # start of the next window in the padded 16 kHz stream
        self._model = np.zeros(LEAD_IN, np.float32)  # padded 16 kHz audio so far
        self.ended = False

    @property
    def padded_audio(self) -> np.ndarray:
        """16 kHz audio including the lead-in, as Ditto sees it."""
        return self._model

    def append_pcm16(self, pcm: bytes) -> None:
        if self.ended:
            raise ValueError("utterance already ended")
        usable = len(pcm) - len(pcm) % 2
        if not usable:
            return
        chunk = np.frombuffer(pcm[:usable], dtype="<i2").astype(np.float32) / 32768.0
        if (self._raw_samples + len(chunk)) / self.rate > MAX_UTTERANCE_SECONDS:
            raise ValueError("utterance too long")
        self._raw.append(chunk)
        self._raw_samples += len(chunk)
        # Resample the whole utterance each time: no filter seams between chunks,
        # and utterances are short enough for this to stay cheap.
        whole = to_model_rate(np.concatenate(self._raw), self.rate)
        self._model = np.concatenate([np.zeros(LEAD_IN, np.float32), whole])

    def end(self) -> None:
        if not self.ended:
            self.ended = True
            tail = np.zeros(int(TAIL_SECONDS * MODEL_RATE), np.float32)
            self._model = np.concatenate([self._model, tail])

    def ready_windows(self) -> list[np.ndarray]:
        """Windows whose audio is complete; after end(), every remaining window."""
        windows = []
        while True:
            stop = self._next + WINDOW
            if stop > len(self._model):
                if not self.ended or self._next >= len(self._model):
                    break
                chunk = np.pad(self._model[self._next:], (0, stop - len(self._model)))
            else:
                chunk = self._model[self._next:stop]
            windows.append(chunk.astype(np.float32, copy=False))
            self._next += STEP
        return windows

    def known_frames(self) -> int:
        """Frames whose audio (plus one frame of lookahead) is already known."""
        return max(0, len(self._model) // SAMPLES_PER_FRAME - 1)


def patch_rect(mask_bbox, frame_size, margin=4):
    """Clamp a (x0, y0, x1, y1) box plus margin to the frame; returns x, y, w, h."""
    x0, y0, x1, y1 = mask_bbox
    width, height = frame_size
    x0, y0 = max(0, x0 - margin), max(0, y0 - margin)
    x1, y1 = min(width, x1 + margin), min(height, y1 + margin)
    # Even sizes keep JPEG chroma subsampling from shifting the edge by a pixel.
    w, h = (x1 - x0) // 2 * 2, (y1 - y0) // 2 * 2
    return int(x0), int(y0), int(w), int(h)
