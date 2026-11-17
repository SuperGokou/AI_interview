"""Lower-face compositor: the model's own mouth, jaw and chin feathered into the portrait.

Chosen over the lip-warp (identity_mouth) and mouth-only (mouth_composite) variants
because it shows real articulation: rounded, open and closed shapes follow the audio.
Everything above the nose, the hair, clothes and background stay the original pixels.
"""
import cv2
import numpy as np

# Mask geometry as fractions of the face box (ellipse centred on the mouth).
# Wide enough to take the cheeks and smile lines from the model as well: keeping
# the portrait's smiling cheeks around a neutral speaking mouth looks pasted on.
# The top edge stays below the box midline, above which the model only
# reconstructs the reference image.
_CENTRE_Y = 0.77
_RADIUS_X = 0.43
_RADIUS_Y = 0.25
_FEATHER = 0.70

# The model renders the face at 256 px, so the patch is softer than the portrait.
_SHARPEN_AMOUNT = 0.6
_SHARPEN_SIGMA = 1.4

# Skin-tone correction measured on the rim of the mask, clamped per channel.
_MAX_TONE_SHIFT = 14.0
_RIM_LOW, _RIM_HIGH = 0.02, 0.22


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
        x1, y1, x2, y2 = self.box
        result = self.frame.copy()
        result[y1:y2, x1:x2] = self.apply_region(patch, speech)
        return result

    def apply_region(self, patch, speech=1.0):
        """Same blend, returning only the face-box pixels. The streaming service
        uses this to avoid copying the full portrait for every frame."""
        speech = float(np.clip(speech, 0, 1))
        if speech <= 0:
            return self.original.astype(np.uint8)
        patch = patch.astype(np.float32)
        blurred = cv2.GaussianBlur(patch, (0, 0), _SHARPEN_SIGMA)
        patch = patch + _SHARPEN_AMOUNT * (patch - blurred)
        shift = np.median(self.original[self.rim] - patch[self.rim], axis=0)
        patch = patch + np.clip(shift, -_MAX_TONE_SHIFT, _MAX_TONE_SHIFT)
        alpha = self.mask * speech
        return np.clip(self.original * (1 - alpha) + patch * alpha, 0, 255).astype(np.uint8)
