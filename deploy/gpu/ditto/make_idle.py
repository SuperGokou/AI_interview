"""Render a seamless idle loop (listening pose: blinks, slight sway) from the portrait.

Driven by quiet room tone, so the mouth stays closed. Expression and pose fade in from
and back out to the portrait itself, so the first and last frames match the still
image and the clip loops without a jump.
"""
import sys, subprocess, numpy as np, soundfile, cv2
from stream_pipeline_offline import StreamSDK
from inference import run
seconds, out = float(sys.argv[1]), sys.argv[2]
rng = np.random.default_rng(7)
soundfile.write("tmp/idle.wav", (rng.standard_normal(int(16000 * seconds)) * 0.0015).astype(np.float32), 16000)
sdk = StreamSDK("./checkpoints/ditto_cfg/v0.4_hubert_cfg_pytorch.pkl", "./checkpoints/ditto_pytorch")
n = int(seconds * 25)
run(sdk, "tmp/idle.wav", "portrait.png", "tmp/idle-raw.mp4", {
    "setup_kwargs": {"relative_d": True, "fade_type": "s", "fade_out_keys": ("exp", "pitch", "yaw", "roll", "t"),
                     "use_d_keys": {"exp": 0.6, "pitch": 0.6, "yaw": 0.6, "roll": 0.3, "t": 0.5}},
    "run_kwargs": {"fade_in": 20, "fade_out": 20},
})
cap = cv2.VideoCapture("tmp/idle-raw.mp4"); frames = []
while True:
    ok, f = cap.read()
    if not ok: break
    frames.append(f)
src = cv2.imread("portrait.png")[: frames[0].shape[0]]
d = lambda f: float(np.abs(f.astype(np.float32) - src.astype(np.float32))[150:450, 700:1050].mean())
motion = [d(f) for f in frames]
print("frames", len(frames), "| first/last frame vs portrait:", round(motion[0], 2), round(motion[-1], 2), "| peak motion:", round(max(motion), 2))
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", "tmp/idle-raw.mp4", "-an", "-c:v", "libx264", "-crf", "17", "-preset", "slow",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], check=True)
