"""Where does the model draw the mouth, compared with the portrait's own mouth?"""
import cv2, numpy as np, torch, sys
from stream_engine import StreamEngine, FACE_BOX
from stream_logic import UtteranceBuffer
import soundfile

engine = StreamEngine(sys.argv[1]) if len(sys.argv) > 1 else StreamEngine()
x1, y1, x2, y2 = FACE_BOX

def lips(face):
    """Centroid and extent of strongly red pixels inside a window around the mouth."""
    wx1, wy1, wx2, wy2 = 790 - x1, 310 - y1, 970 - x1, 410 - y1
    win = face[wy1:wy2, wx1:wx2]
    b, g, r = [c.astype(np.float32) for c in cv2.split(win)]
    score = np.clip((r - g) - 55, 0, None) * ((r - b) > 40)
    if score.sum() < 1:
        return (0, 0, 0, 0, 0)
    ys, xs = np.mgrid[0:win.shape[0], 0:win.shape[1]]
    cx = (score * xs).sum() / score.sum() + wx1 + x1
    cy = (score * ys).sum() / score.sum() + wy1 + y1
    cols = np.nonzero(score.sum(0) > score.sum(0).max() * 0.15)[0]
    rows = np.nonzero(score.sum(1) > score.sum(1).max() * 0.15)[0]
    return (round(float(cx), 1), round(float(cy), 1), int(cols.max() - cols.min()), int(rows.max() - rows.min()), int((score > 0).sum()))

print("portrait lips  (cx, cy, width, height, pixels):", lips(engine.frame[y1:y2, x1:x2]))
audio, rate = soundfile.read("sample-long.wav", dtype="int16")
buf = UtteranceBuffer(rate); buf.append_pcm16(audio.tobytes()); buf.end()
source, frames = buf.snapshot(340)
from stream_logic import resample_to_model_rate
with torch.inference_mode():
    prompts = engine._audio_prompts(resample_to_model_rate(source, rate), frames)
    stats = []
    for off in range(0, len(frames), 16):
        batch = prompts[off:off + 16]
        lat = engine.latent.expand(len(batch), -1, -1, -1).to(dtype=torch.float16)
        pred = engine.unet.model(lat, engine.steps, encoder_hidden_states=engine.pe(batch)).sample
        for img in engine.vae.decode_latents(pred):
            face = cv2.resize(img, (x2 - x1, y2 - y1), interpolation=cv2.INTER_CUBIC)
            stats.append(lips(face))
stats = np.array(stats, dtype=np.float32)
closed = stats[stats[:, 3] <= np.percentile(stats[:, 3], 25)]  # the flattest mouths: closed lips
print("generated lips, all frames   median (cx, cy, width, height):", np.median(stats[:, :4], axis=0).round(1))
print("generated lips, closed mouth median (cx, cy, width, height):", np.median(closed[:, :4], axis=0).round(1))
print("generated cx range:", stats[:, 0].min(), stats[:, 0].max(), "| cy range:", stats[:, 1].min(), stats[:, 1].max())
