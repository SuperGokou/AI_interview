"""GPU side of streaming lip-sync: render a range of frames for a growing utterance.

One engine owns the models and is shared by every connection; calls are serialised
by a lock because they share the GPU. Run from the MuseTalk checkout.
"""
import math
import os
import threading

import cv2
import numpy as np
import torch
from einops import rearrange
from transformers import AutoFeatureExtractor, WhisperModel

from lower_face import LowerFace
from musetalk.utils.utils import load_all_model
from stream_logic import FPS, MODEL_RATE, UtteranceBuffer, resample_to_model_rate

PORTRAIT_WIDTH = 1672
PORTRAIT_HEIGHTS = (941, 942)  # the still portrait, or a frame of the page's base video
FACE_BOX = (750, 139, 990, 419)
JPEG_QUALITY = 90
PATCH_MARGIN = 4
BATCH = 8
# Frames per render() call. Small, so frames are sent while later ones are still
# rendering and concurrent sessions take turns on the GPU.
MAX_FRAMES_PER_CALL = 8

_SEGMENT = 30 * MODEL_RATE
_AUDIO_FPS = 50
_PAD_LEFT, _PAD_RIGHT = 4, 12  # encoder positions, as in MuseTalk's get_whisper_chunk
_WINDOW = 10


class StreamEngine:
    def __init__(self, portrait=None, whisper_dir="models/whisper"):
        # Render against the very picture the page shows underneath. The page's base
        # layer is a video whose tone and position differ slightly from the still
        # portrait; PORTRAIT lets the service use a frame of that video instead.
        portrait = portrait or os.environ.get("PORTRAIT", "zoom-interviewer-listening.png")
        torch.set_num_threads(4)
        torch.manual_seed(42)
        self.device = torch.device("cuda:0")
        self.vae, self.unet, self.pe = load_all_model(device=self.device)
        self.vae.vae.half()
        self.unet.model.half()
        self.pe = self.pe.half().to(self.device)
        self.whisper = WhisperModel.from_pretrained(whisper_dir).half().to(self.device).eval()
        self.extractor = AutoFeatureExtractor.from_pretrained(whisper_dir)
        frame = cv2.imread(str(portrait))
        if frame is None or frame.shape[1] != PORTRAIT_WIDTH or frame.shape[0] not in PORTRAIT_HEIGHTS:
            raise ValueError("Expected the 1672-wide interviewer portrait (941 or 942 high)")
        self.frame = frame
        self.size = (frame.shape[1], frame.shape[0])
        x1, y1, x2, y2 = FACE_BOX
        with torch.inference_mode():
            self.latent = self.vae.get_latents_for_unet(cv2.resize(frame[y1:y2, x1:x2], (256, 256)))
        self.compositor = LowerFace(frame, FACE_BOX)
        self.patch = self._patch_rect()
        self.steps = torch.tensor([0], device=self.device)
        self._lock = threading.Lock()
        self.render(self._warmup_buffer())  # first call pays CUDA initialisation

    def describe(self) -> dict:
        x, y, w, h = self.patch
        return {
            "fps": FPS,
            "frame": {"width": self.size[0], "height": self.size[1]},
            "patch": {"x": x, "y": y, "width": w, "height": h},
        }

    def _patch_rect(self):
        """Smallest rectangle (portrait coordinates) containing every blended pixel.

        Clamped to the face box: frames are cut from the box-sized blend, so a
        rectangle reaching outside it would announce a size the JPEGs do not have
        and the browser would stretch them."""
        ys, xs = np.nonzero(self.compositor.mask[..., 0] > 0)
        x1, y1, x2, y2 = FACE_BOX
        left = max(x1, x1 + int(xs.min()) - PATCH_MARGIN)
        top = max(y1, y1 + int(ys.min()) - PATCH_MARGIN)
        right = min(x2, x1 + int(xs.max()) + 1 + PATCH_MARGIN)
        bottom = min(y2, y1 + int(ys.max()) + 1 + PATCH_MARGIN)
        return left, top, right - left, bottom - top

    @staticmethod
    def _warmup_buffer() -> UtteranceBuffer:
        buffer = UtteranceBuffer(MODEL_RATE)
        buffer.append_pcm16((np.zeros(MODEL_RATE // 2, "<i2")).tobytes())
        buffer.end()
        return buffer

    @torch.inference_mode()
    def _audio_prompts(self, audio: np.ndarray, frames: range) -> torch.Tensor:
        """Per-frame audio conditioning, equivalent to MuseTalk's get_whisper_chunk
        restricted to `frames`."""
        encoded = []
        for start in range(0, max(len(audio), 1), _SEGMENT):
            mel = self.extractor(audio[start:start + _SEGMENT], return_tensors="pt",
                                 sampling_rate=MODEL_RATE).input_features
            hidden = self.whisper.encoder(mel.to(self.device, dtype=torch.float16),
                                          output_hidden_states=True).hidden_states
            encoded.append(torch.stack(hidden, dim=2))
        feature = torch.cat(encoded, dim=1)[:, :math.floor(len(audio) / MODEL_RATE * _AUDIO_FPS)]
        feature = torch.cat([
            torch.zeros_like(feature[:, :1]).expand(-1, _PAD_LEFT, -1, -1),
            feature,
            torch.zeros_like(feature[:, :1]).expand(-1, _PAD_RIGHT, -1, -1),
        ], dim=1)
        step = _AUDIO_FPS // FPS
        clips = [feature[:, f * step:f * step + _WINDOW] for f in frames]
        return rearrange(torch.cat(clips, dim=0), "b c h w -> b (c h) w")

    @torch.inference_mode()
    def render(self, buffer: UtteranceBuffer) -> list[tuple[int, bytes]]:
        """Render every frame that is ready; returns (frame index, JPEG of the patch)."""
        with self._lock:
            source, frames = buffer.snapshot(MAX_FRAMES_PER_CALL)
            if not len(frames):
                return []
            audio = resample_to_model_rate(source, buffer.rate)
            prompts = self._audio_prompts(audio, frames)
            gate = buffer.gate_for(frames, source)
            x1, y1, x2, y2 = FACE_BOX
            px, py, pw, ph = self.patch
            px, py = px - x1, py - y1  # patch origin inside the face box
            output: list[tuple[int, bytes]] = []
            for offset in range(0, len(frames), BATCH):
                batch = prompts[offset:offset + BATCH]
                latents = self.latent.expand(len(batch), -1, -1, -1).to(dtype=torch.float16)
                predicted = self.unet.model(latents, self.steps, encoder_hidden_states=self.pe(batch)).sample
                for k, image in enumerate(self.vae.decode_latents(predicted)):
                    index = frames.start + offset + k
                    face = cv2.resize(image, (x2 - x1, y2 - y1), interpolation=cv2.INTER_CUBIC)
                    composed = self.compositor.apply_region(face, gate[offset + k])
                    region = composed[py:py + ph, px:px + pw]
                    if region.shape[:2] != (ph, pw):
                        raise RuntimeError("patch does not match its announced size")
                    ok, jpeg = cv2.imencode(".jpg", region, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                    if not ok:
                        raise RuntimeError("JPEG encoding failed")
                    output.append((index, jpeg.tobytes()))
            buffer.mark_rendered(frames)
            return output
