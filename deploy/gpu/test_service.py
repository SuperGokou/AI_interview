import importlib.util
import io
from pathlib import Path
import sys
import wave
from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location('gpu_service', Path(__file__).with_name('service.py'))
service = importlib.util.module_from_spec(spec)
if Path(spec.origin).exists():
    spec.loader.exec_module(service)

def wave_bytes(seconds=1):
    buf=io.BytesIO()
    with wave.open(buf,'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
        wav.writeframes(b'\0\0'*24000*seconds)
    return buf.getvalue()

def make_client(tmp_path):
    assert hasattr(service, 'create_app'), 'GPU service factory is not implemented'
    def render(audio, output):
        Path(output).write_bytes(b'test-mp4')
    return TestClient(service.create_app(render, 'test-private-key', tmp_path))

def test_auth_required_before_render(tmp_path):
    with make_client(tmp_path) as client:
        assert client.post('/render', content=wave_bytes()).status_code == 401
        assert client.post('/render', headers={'Authorization':'Bearer wrong'},content=wave_bytes()).status_code == 401

def test_bad_or_long_audio_rejected(tmp_path):
    with make_client(tmp_path) as client:
        headers={'Authorization':'Bearer test-private-key'}
        assert client.post('/render',headers=headers,content=b'bad').status_code == 400
        assert client.post('/render',headers=headers,content=wave_bytes(31)).status_code == 413

def test_success_returns_video_and_removes_temporary_files(tmp_path):
    with make_client(tmp_path) as client:
        result=client.post('/render',headers={'Authorization':'Bearer test-private-key'},content=wave_bytes())
        assert result.status_code == 200
        assert result.headers['content-type'] == 'video/mp4'
        assert result.content == b'test-mp4'
        assert not list(tmp_path.iterdir())

def test_render_failure_returns_503_and_cleans_up(tmp_path):
    assert hasattr(service,'create_app'), 'GPU service factory is not implemented'
    def fail(audio, output):
        raise RuntimeError('synthetic CUDA failure')
    with TestClient(service.create_app(fail,'key',tmp_path)) as client:
        result=client.post('/render',headers={'Authorization':'Bearer key'},content=wave_bytes())
        assert result.status_code == 503
        assert not list(tmp_path.iterdir())

def test_busy_gpu_rejects_second_request_without_queueing(tmp_path):
    import concurrent.futures
    import threading
    entered=threading.Event()
    release=threading.Event()
    def render(audio,output):
        entered.set()
        assert release.wait(5)
        Path(output).write_bytes(b'mp4')
    with TestClient(service.create_app(render,'key',tmp_path)) as client:
        def call():
            return client.post('/render',headers={'Authorization':'Bearer key'},content=wave_bytes())
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            first=pool.submit(call)
            assert entered.wait(5)
            try:
                assert call().status_code == 429
            finally:
                release.set()
            assert first.result().status_code == 200
