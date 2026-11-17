import unittest

import numpy as np

from speech_gate import HOLD_FRAMES, SpeechGate, gate_levels

RATE, FPS = 16000, 25
PER_FRAME = RATE // FPS


def clip(*parts):
    """parts: (seconds, amplitude) pairs."""
    return np.concatenate([np.full(int(s * RATE), a, np.float32) for s, a in parts])


class SpeechGateTests(unittest.TestCase):
    def test_closed_in_silence_and_opens_quickly_for_speech(self):
        gate = gate_levels(clip((1.0, 0.0), (1.0, 0.1)), RATE, FPS, 50)
        self.assertTrue(np.all(gate[:23] == 0))
        self.assertGreater(gate[27], 0.99)  # open within ~3 frames of the onset

    def test_short_pause_inside_a_sentence_keeps_the_mouth_generated(self):
        gate = gate_levels(clip((1.0, 0.1), (0.4, 0.0), (1.0, 0.1)), RATE, FPS, 60)
        self.assertGreater(gate[25:35].min(), 0.99)

    def test_long_silence_eases_back_to_the_portrait(self):
        gate = gate_levels(clip((1.0, 0.1), (2.0, 0.0)), RATE, FPS, 75)
        closing = gate[25 + HOLD_FRAMES:]
        self.assertEqual(closing[-1], 0)
        self.assertTrue(np.all(np.diff(closing) <= 0))
        self.assertLessEqual(float(np.abs(np.diff(gate)).max()), 0.35)  # never a hard cut

    def test_incremental_matches_offline(self):
        audio = clip((0.5, 0.0), (0.7, 0.1), (1.2, 0.0), (0.4, 0.1))
        offline = gate_levels(audio, RATE, FPS, 70)
        gate = SpeechGate()
        from speech_gate import frame_is_active
        online = [gate.step(frame_is_active(audio, i, PER_FRAME) or frame_is_active(audio, i + 1, PER_FRAME))
                  for i in range(70)]
        np.testing.assert_allclose(online, offline)


if __name__ == "__main__":
    unittest.main()
