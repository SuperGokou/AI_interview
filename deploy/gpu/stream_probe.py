"""Measure the streaming lip-sync service the way the interview backend uses it.

Feeds a WAV file in chunks at a chosen speed (the realtime speech model delivers
audio faster than real time) and reports, per frame, how long after its audio
position the frame arrived. The worst value is the playback delay a client needs.

  python stream_probe.py --audio sample.wav --speed 4 [--save out.mp4]
Reads GPU_API_KEY from the environment.
"""
import argparse
import asyncio
import json
import os
import subprocess
import time
import wave

import websockets

from stream_logic import FPS, unpack_frame

CHUNK_SECONDS = 0.1


async def run(args):
    with wave.open(args.audio, "rb") as wav:
        rate, pcm = wav.getframerate(), wav.readframes(wav.getnframes())
    chunk = int(rate * CHUNK_SECONDS) * 2
    headers = {"Authorization": f"Bearer {os.environ['GPU_API_KEY']}"}
    async with websockets.connect(f"{args.url}?rate={rate}", additional_headers=headers,
                                  max_size=None) as ws:
        ready = json.loads(await ws.recv())
        arrivals, frames = {}, {}
        started = time.monotonic()

        async def feed():
            for offset in range(0, len(pcm), chunk):
                await ws.send(pcm[offset:offset + chunk])
                await asyncio.sleep(CHUNK_SECONDS / args.speed)
            await ws.send(json.dumps({"type": "end"}))

        feeder = asyncio.create_task(feed())
        while True:
            message = await ws.recv()
            if isinstance(message, bytes):
                _, index, jpeg = unpack_frame(message)
                arrivals[index] = time.monotonic() - started
                frames[index] = jpeg
            elif json.loads(message)["type"] == "done":
                break
        await feeder
    total = time.monotonic() - started
    lateness = sorted(arrivals[i] - i / FPS for i in arrivals)
    report = {
        "speed": args.speed,
        "audio_s": round(len(pcm) / 2 / rate, 2),
        "frames": len(arrivals),
        "contiguous": sorted(arrivals) == list(range(len(arrivals))),
        "wall_s": round(total, 2),
        "first_frame_ms": round(arrivals[0] * 1000),
        "needed_delay_ms": round(max(lateness) * 1000),
        "p95_delay_ms": round(lateness[int(len(lateness) * 0.95)] * 1000),
        "avg_jpeg_bytes": round(sum(map(len, frames.values())) / len(frames)),
        "patch": ready["patch"],
    }
    print(json.dumps(report))
    if args.save:
        save(args, ready, frames)


def save(args, ready, frames):
    """Rebuild full frames the way the browser does, to check the patches visually."""
    import cv2
    import numpy as np

    portrait = cv2.imread("zoom-interviewer-listening.png")
    p = ready["patch"]
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "1672x941",
           "-r", str(FPS), "-i", "pipe:0", "-i", args.audio, "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-shortest", args.save]
    encoder = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for index in sorted(frames):
        frame = portrait.copy()
        patch = cv2.imdecode(np.frombuffer(frames[index], np.uint8), cv2.IMREAD_COLOR)
        frame[p["y"]:p["y"] + p["height"], p["x"]:p["x"] + p["width"]] = patch
        encoder.stdin.write(frame.tobytes())
    encoder.stdin.close()
    encoder.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--url", default="ws://127.0.0.1:8765/stream")
    parser.add_argument("--speed", type=float, default=4.0)
    parser.add_argument("--save")
    asyncio.run(run(parser.parse_args()))
