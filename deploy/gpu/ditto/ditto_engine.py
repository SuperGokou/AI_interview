"""Streaming Ditto renderer for the interview page. Run from the ditto-talkinghead checkout.

Settings are the 'R2' configuration approved on rendered samples:
  - the model's own expression for the lips (keeps the mouth straight),
  - half head motion and no head roll,
  - in pauses (and after each utterance) the face eases back to the portrait,
  - 20 diffusion steps, a new motion window every 10 frames, the motion model
    compiled with torch.compile (about 3x faster per step).

One engine renders one utterance at a time; the service gives it one session.
"""
import os
import threading
import time

import cv2
import numpy as np
import torch

import core.atomic_components.writer as writer_module
import queue

from ditto_logic import CHUNKSIZE, END_FALL_PER_FRAME, FPS, AudioWindows, Pacer, patch_rect
from speech_gate import SpeechGate, frame_is_active
from stream_pipeline_online import StreamSDK

CFG = "./checkpoints/ditto_cfg/v0.4_hubert_cfg_pytorch.pkl"
DATA = "./checkpoints/ditto_pytorch"
JPEG_QUALITY = 88
SETUP = {
    "online_mode": True,
    "overlap_v2": 70,
    "sampling_timesteps": 20,
    "relative_d": False,
    "use_d_keys": {"exp": 1, "pitch": 0.5, "yaw": 0.5, "roll": 0.0, "t": 0.5},
    "fade_type": "s",
    # Pose too, so the last frame of an utterance is the portrait itself and the
    # page can switch back to the still image without a jump.
    "fade_out_keys": ("exp", "pitch", "yaw", "roll", "t"),
}


class _FrameSink:
    """Stands in for Ditto's video file writer and hands frames to a callback."""

    def __init__(self, *_args, **_kwargs):
        self.on_frame = None

    def __call__(self, img, fmt="rgb"):
        if self.on_frame is not None:
            self.on_frame(img if fmt == "rgb" else img[..., ::-1])

    def close(self):
        pass


class _PacedSDK(StreamSDK):
    """StreamSDK whose render stages skip frames when a reply has fallen behind.

    Warping and decoding are the expensive per-frame steps. A skipped frame goes
    through as a marker so the frame numbering the browser relies on stays intact.
    """

    pacer: Pacer | None = None
    on_skip = None

    def _warp_f3d_worker(self):
        produced = 0
        while not self.stop_event.is_set():
            try:
                item = self.warp_f3d_queue.get(timeout=1)
            except queue.Empty:
                continue
            if item is None:
                self.decode_f3d_queue.put(None)
                break
            frame_idx, x_s, x_d = item
            if self.pacer is not None and self.pacer.should_skip(produced, time.monotonic()):
                self.decode_f3d_queue.put([frame_idx, None])
            else:
                f_s = self.source_info["f_s_lst"][frame_idx]
                self.decode_f3d_queue.put([frame_idx, self.warp_f3d(f_s, x_s, x_d)])
            produced += 1

    def _decode_f3d_worker(self):
        while not self.stop_event.is_set():
            try:
                item = self.decode_f3d_queue.get(timeout=1)
            except queue.Empty:
                continue
            if item is None:
                self.putback_queue.put(None)
                break
            frame_idx, f_3d = item
            self.putback_queue.put([frame_idx, None if f_3d is None else self.decode_f3d(f_3d)])

    def _putback_worker(self):
        while not self.stop_event.is_set():
            try:
                item = self.putback_queue.get(timeout=1)
            except queue.Empty:
                continue
            if item is None:
                self.writer_queue.put(None)
                break
            frame_idx, render_img = item
            if render_img is None:
                if self.on_skip is not None:
                    self.on_skip()
                continue
            frame_rgb = self.source_info["img_rgb_lst"][frame_idx]
            M_c2o = self.source_info["M_c2o_lst"][frame_idx]
            self.writer_queue.put(self.putback(frame_rgb, render_img, M_c2o))


class DittoEngine:
    def __init__(self, portrait=None):
        self.portrait = portrait or os.environ.get("PORTRAIT", "portrait.png")
        writer_module.VideoWriterByImageIO = _FrameSink
        import stream_pipeline_online
        stream_pipeline_online.VideoWriterByImageIO = _FrameSink
        self.sdk = _PacedSDK(CFG, DATA)
        self._preempt = threading.Event()
        self._cache_avatar()
        self._compile_motion_model()
        self._lock = threading.Lock()
        self._active = False
        self._warm_up()
        self.frame_size, self.patch = self._geometry()

    # ---- setup -------------------------------------------------------------

    def _cache_avatar(self):
        """Face detection and feature extraction are the same for every utterance."""
        registrar, cache = self.sdk.avatar_registrar, {}

        def cached(source_path, **kwargs):
            key = (source_path, tuple(sorted((k, str(v)) for k, v in kwargs.items())))
            if key not in cache:
                cache[key] = registrar(source_path, **kwargs)
            return cache[key]

        self.sdk.avatar_registrar = cached

    def _compile_motion_model(self):
        model = self.sdk.audio2motion.lmdm.model.model
        compiled = torch.compile(model.guided_forward, mode="default", dynamic=False)
        model.guided_forward = compiled

    def _warm_up(self):
        started = time.monotonic()
        frames = []
        self.start(lambda index, jpeg: frames.append(index), rate=16000, encode=False)
        noise = (np.random.randn(16000 * 2) * 1500).astype("<i2").tobytes()
        self.feed(noise)
        self.finish()
        print(f"warm-up rendered {len(frames)} frames in {time.monotonic() - started:.1f}s", flush=True)

    def _geometry(self):
        info = self.sdk.source_info
        height, width = info["img_rgb_lst"][0].shape[:2]
        mask = cv2.warpAffine(self.sdk.putback.mask_ori_float, info["M_c2o_lst"][0][:2, :], (width, height))
        ys, xs = np.nonzero(mask > 0.002)
        return (width, height), patch_rect((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1), (width, height))

    def describe(self) -> dict:
        x, y, w, h = self.patch
        return {"fps": FPS, "frame": {"width": self.frame_size[0], "height": self.frame_size[1]},
                "patch": {"x": x, "y": y, "width": w, "height": h}}

    # ---- one utterance -------------------------------------------------------

    def start(self, on_frame, rate=24000, encode=True):
        """Begin an utterance. on_frame(index, jpeg_bytes) is called from a worker thread."""
        with self._lock:
            if self._active:
                raise RuntimeError("an utterance is already being rendered")
            self._active = True
        self._audio = AudioWindows(rate)
        self._gate, self._gated = SpeechGate(), 0
        self._ctrl: dict[int, dict] = {}
        self._index = 0
        self._preempt.clear()
        self.sdk.pacer = Pacer()

        def skipped():
            self._index += 1  # keep numbering in step with the audio

        self.sdk.on_skip = skipped

        def sink(rgb):
            index = self._index
            self._index += 1
            if not encode:
                on_frame(index, b"")
                return
            x, y, w, h = getattr(self, "patch", (0, 0, rgb.shape[1], rgb.shape[0]))
            region = np.ascontiguousarray(rgb[y:y + h, x:x + w, ::-1])
            ok, jpeg = cv2.imencode(".jpg", region, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ok:
                on_frame(index, jpeg.tobytes())

        self.sdk.setup(self.portrait, "/tmp/ditto-stream.mp4", ctrl_info=self._ctrl, **SETUP)
        self.sdk.writer.on_frame = sink
        self.sdk.setup_Nd(N_d=-1, ctrl_info=self._ctrl)

    def feed(self, pcm: bytes) -> None:
        self._audio.append_pcm16(pcm)
        self._advance()

    def finish(self) -> None:
        """Flush the utterance; returns after its last frame has been delivered,
        or as soon as preempt() is called because the next reply has started."""
        try:
            speech_frames = self._audio.known_frames()
            self._audio.end()
            self._advance()
            self.sdk.audio2motion_queue.put(None)
            while any(thread.is_alive() for thread in self.sdk.thread_list):
                # Only the closing fade may be cut short; frames that belong to
                # speech the candidate is still hearing are always delivered.
                if self._preempt.is_set() and self._index >= speech_frames:
                    self.sdk.stop_event.set()
                for thread in self.sdk.thread_list:
                    thread.join(timeout=0.02)
            if self.sdk.worker_exception is not None and not self._preempt.is_set():
                raise self.sdk.worker_exception
        finally:
            self._active = False

    def preempt(self) -> None:
        """Thread-safe: cut the closing frames of the current utterance short."""
        self._preempt.set()

    def abort(self) -> None:
        try:
            self.sdk.stop_event.set()
            for thread in self.sdk.thread_list:
                thread.join(timeout=5)
        finally:
            self._active = False

    def _advance(self):
        audio = self._audio.padded_audio
        per_frame = 640
        while self._gated < self._audio.known_frames():
            i = self._gated
            active = frame_is_active(audio, i, per_frame) or frame_is_active(audio, i + 1, per_frame)
            self._ctrl[i] = {"fade_alpha": float(self._gate.step(active))}
            self._gated += 1
        if self._audio.ended:  # settle to the portrait quickly, without the pause hold
            level = self._gate.level
            for i in range(max(0, self._gated - int(0.5 * FPS)), self._gated + 60):
                level = max(0.0, min(level, self._ctrl.get(i, {}).get("fade_alpha", level)) - END_FALL_PER_FRAME)
                self._ctrl[i] = {"fade_alpha": level}
        for window in self._audio.ready_windows():
            self.sdk.run_chunk(window, CHUNKSIZE)
