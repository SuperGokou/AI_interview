import unittest

import numpy as np

from lower_face import LowerFace

BOX = (750, 139, 990, 419)


def portrait(value=150):
    return np.full((941, 1672, 3), value, np.uint8)


def patch(value):
    return np.full((BOX[3] - BOX[1], BOX[2] - BOX[0], 3), value, np.uint8)


class LowerFaceTests(unittest.TestCase):
    def test_silence_returns_the_original_portrait(self):
        frame = portrait()
        result = LowerFace(frame, BOX).apply(patch(20), speech=0)
        np.testing.assert_array_equal(result, frame)
        self.assertIsNot(result, frame)  # callers may write into the returned frame

    def test_only_the_lower_face_changes(self):
        frame = portrait()
        result = LowerFace(frame, BOX).apply(self.mouth_patch(), speech=1)
        x1, y1, x2, y2 = BOX
        nose_line = y1 + int((y2 - y1) * 0.50)  # model only regenerates below this
        np.testing.assert_array_equal(result[:nose_line], frame[:nose_line])  # eyes, nose, hair
        np.testing.assert_array_equal(result[y2:], frame[y2:])  # neck and clothes
        np.testing.assert_array_equal(result[:, :x1], frame[:, :x1])
        np.testing.assert_array_equal(result[:, x2:], frame[:, x2:])
        self.assertTrue((result != frame).any())

    def test_region_matches_the_full_frame_blend(self):
        frame = portrait()
        compositor = LowerFace(frame, BOX)
        x1, y1, x2, y2 = BOX
        for speech in (0, 0.5, 1):
            full = compositor.apply(self.mouth_patch(), speech)
            np.testing.assert_array_equal(
                compositor.apply_region(self.mouth_patch(), speech), full[y1:y2, x1:x2]
            )

    def test_mask_edge_is_seamless(self):
        compositor = LowerFace(portrait(), BOX)
        mask = compositor.mask[..., 0]
        self.assertEqual(mask[0].max(), 0)
        self.assertEqual(mask[:, 0].max(), 0)
        self.assertEqual(mask[:, -1].max(), 0)
        self.assertAlmostEqual(float(mask.max()), 1.0, places=5)
        self.assertLess(float(np.abs(np.diff(mask, axis=0)).max()), 0.08)  # no hard step

    def test_skin_tone_is_matched_to_the_portrait(self):
        frame = portrait(150)
        # A uniformly darker generated face must not leave a dark oval on the portrait.
        result = LowerFace(frame, BOX).apply(patch(140), speech=1)
        self.assertLessEqual(int(np.abs(result.astype(int) - 150).max()), 1)

    def test_partial_speech_blends_proportionally(self):
        frame = portrait(150)
        compositor = LowerFace(frame, BOX)
        full = compositor.apply(self.mouth_patch(), speech=1).astype(int)
        half = compositor.apply(self.mouth_patch(), speech=0.5).astype(int)
        changed = np.abs(full - 150) > 20
        self.assertTrue(changed.any())
        ratio = np.abs(half - 150)[changed].mean() / np.abs(full - 150)[changed].mean()
        self.assertAlmostEqual(ratio, 0.5, delta=0.05)

    @staticmethod
    def mouth_patch():
        p = patch(150)
        height, width = p.shape[:2]
        cy, cx = int(height * 0.74), width // 2
        p[cy - 8:cy + 8, cx - 30:cx + 30] = (60, 60, 190)  # red lips on matching skin
        return p


if __name__ == "__main__":
    unittest.main()
