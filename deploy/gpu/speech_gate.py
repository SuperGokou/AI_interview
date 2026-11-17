"""Speech gate: how strongly the generated mouth replaces the portrait, per video frame.

The portrait smiles while the generated speaking mouth is neutral, so every switch
between the two is a visible change of expression. The gate therefore:
  - opens over a few frames when speech starts,
  - stays open through the short pauses inside a sentence (the model draws a natural
    closed mouth there), and
  - only eases back to the portrait after a sustained silence.
"""
import numpy as np

ENERGY_THRESHOLD = 0.008  # RMS of float audio in [-1, 1]
RISE_PER_FRAME = 0.34  # fully open in 3 frames (120 ms)
FALL_PER_FRAME = 0.09  # fully closed in about 11 frames (450 ms)
HOLD_FRAMES = 15  # 600 ms of silence before closing starts


def frame_is_active(audio: np.ndarray, index: int, samples_per_frame: float) -> bool:
    block = audio[int(index * samples_per_frame):int((index + 1) * samples_per_frame)]
    if not len(block):
        return False
    return float(np.sqrt(np.mean(block.astype(np.float64) ** 2))) > ENERGY_THRESHOLD


class SpeechGate:
    """Incremental: call step() once per frame, in order."""

    def __init__(self):
        self.level = 0.0
        self._quiet_frames = HOLD_FRAMES  # start closed

    def step(self, active: bool) -> float:
        if active:
            self._quiet_frames = 0
            self.level = min(1.0, self.level + RISE_PER_FRAME)
        else:
            self._quiet_frames += 1
            if self._quiet_frames > HOLD_FRAMES:
                self.level = max(0.0, self.level - FALL_PER_FRAME)
        return self.level


def gate_levels(audio: np.ndarray, sample_rate: int, fps: int, count: int) -> np.ndarray:
    """Gate for a complete clip. Looks one frame ahead so the mouth opens on time."""
    per_frame = sample_rate / fps
    gate = SpeechGate()
    return np.array([
        gate.step(frame_is_active(audio, i, per_frame) or frame_is_active(audio, i + 1, per_frame))
        for i in range(count)
    ])
