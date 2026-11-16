"""Private, bounded MuseTalk rendering endpoint. Bind only to loopback."""
import io
import logging
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import threading
import wave
from fastapi import FastAPI, HTTPException, Request
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse

MAX_BYTES=3_000_000

def create_app(render, api_key, output_dir):
    if not api_key:
        raise ValueError('A private GPU_API_KEY is required')
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    busy=threading.Lock()
    output_dir=Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)

    @app.get('/health')
    def health():
        return {'ready':True,'busy':busy.locked()}

    @app.post('/render')
    async def generate(request: Request):
        if not secrets.compare_digest(request.headers.get('authorization',''),f'Bearer {api_key}'):
            raise HTTPException(401,'Unauthorized')
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>MAX_BYTES:
                raise HTTPException(413,'Audio too large')
        try:
            with wave.open(io.BytesIO(body),'rb') as wav:
                if wav.getnchannels()!=1 or wav.getsampwidth()!=2 or wav.getframerate() not in (16000,24000):
                    raise HTTPException(400,'Expected mono PCM16 WAV at 16 or 24 kHz')
                duration=wav.getnframes()/wav.getframerate()
                if duration>30:
                    raise HTTPException(413,'Maximum duration is 30 seconds')
                if duration<.2 or len(wav.readframes(wav.getnframes()))!=wav.getnframes()*2:
                    raise HTTPException(400,'Truncated or empty audio')
        except (wave.Error,EOFError):
            raise HTTPException(400,'Invalid WAV')
        if not busy.acquire(blocking=False):
            raise HTTPException(429,'GPU busy; retry or use audio fallback')
        folder=Path(tempfile.mkdtemp(prefix='render-',dir=output_dir))
        audio=folder/'input.wav'
        output=folder/'output.mp4'
        try:
            audio.write_bytes(body)
            await run_in_threadpool(render,audio,output)
            return FileResponse(output,media_type='video/mp4',background=BackgroundTask(shutil.rmtree,folder))
        except Exception:
            shutil.rmtree(folder,ignore_errors=True)
            logging.exception('GPU render failed')
            raise HTTPException(503,'Renderer unavailable')
        finally:
            busy.release()
    return app

if __name__=='__main__':
    import uvicorn
    from render_portrait import PortraitRenderer
    renderer=PortraitRenderer('zoom-interviewer-listening.png')
    renderer.render('kunyao-test.wav','results/warmup.mp4')
    Path('results/warmup.mp4').unlink(missing_ok=True)
    app=create_app(renderer.render,os.environ['GPU_API_KEY'],'results/api')
    uvicorn.run(app,host='127.0.0.1',port=8765,workers=1)
