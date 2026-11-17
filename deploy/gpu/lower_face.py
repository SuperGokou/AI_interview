"""Lower-face compositor: the model's own mouth, jaw and chin feathered into the portrait.

Chosen over the lip-warp (identity_mouth) and mouth-only (mouth_composite) variants
because it shows real articulation: rounded, open and closed shapes follow the audio.
Everything above the nose, the hair, clothes and background stay the original pixels.
"""
import cv2
import numpy as np

# Mask geometry as fractions of the face box (ellipse centred on the mouth).
_CENTRE_Y = 0.74
_RADIUS_X = 0.36
_RADIUS_Y = 0.22
_FEATHER = 0.55

# The model renders the face at 256 px, so the patch is softer than the portrait.
_SHARPEN_AMOUNT = 0.7
_SHARPEN_SIGMA = 1.4

# Skin-tone correction measured on the rim of the mask, clamped per channel.
_MAX_TONE_SHIFT = 14.0
_RIM_LOW, _RIM_HIGH = 0.03, 0.30


class LowerFace:
    def __init__(self, frame, box):
        self.frame = frame
        self.box = box
        x1, y1, x2, y2 = box
        width, height = x2 - x1, y2 - y1
        self.original = frame[y1:y2, x1:x2].astype(np.float32)
        yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
        radius = ((xx - width / 2) / (width * _RADIUS_X)) ** 2 + (
            (yy - height * _CENTRE_Y) / (height * _RADIUS_Y)
        ) ** 2
        mask = np.clip((1 - radius) / _FEATHER, 0, 1)
        self.mask = (mask * mask * (3 - 2 * mask))[..., None]  # smoothstep edge
        self.rim = (self.mask[..., 0] > _RIM_LOW) & (self.mask[..., 0] < _RIM_HIGH)

    def apply(self, patch, speech=1.0):
        """Blend a generated face patch (already resized to the box) into the portrait.

        speech in [0, 1] fades the generated mouth out during silence, so the
        interviewer returns to her original closed-mouth expression between sentences.
        """
        speech = float(np.clip(speech, 0, 1))
        if speech <= 0:
            return self.frame.copy()
        patch = patch.astype(np.float32)
        blurred = cv2.GaussianBlur(patch, (0, 0), _SHARPEN_SIGMA)
        patch = patch + _SHARPEN_AMOUNT * (patch - blurred)
        shift = np.median(self.original[self.rim] - patch[self.rim], axis=0)
        patch = patch + np.clip(shift, -_MAX_TONE_SHIFT, _MAX_TONE_SHIFT)
        alpha = self.mask * speech
        x1, y1, x2, y2 = self.box
        result = self.frame.copy()
        result[y1:y2, x1:x2] = np.clip(
            self.original * (1 - alpha) + patch * alpha, 0, 255
        ).astype(np.uint8)
        return result
