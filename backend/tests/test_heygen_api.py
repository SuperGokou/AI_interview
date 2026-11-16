"""HeyGen token 接口测试 — 使用 MockTransport 离线验证。"""

import httpx
import pytest

import app.config as config_module
from app.api import heygen as heygen_mod


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "hk-test")
    config_module.get_settings.cache_clear()
    yield
    config_module.get_settings.cache_clear()


def _mock_client(handler):
    transport = httpx.MockTransport(handler)
    return lambda: httpx.Client(transport=transport, timeout=5.0)


def test_token_success(client, monkeypatch):
    def handler(request):
        assert request.headers.get("x-api-key") == "hk-test"
        assert request.url.path == "/v1/streaming.create_token"
        return httpx.Response(200, json={"data": {"token": "sess-123"}})

    monkeypatch.setattr(heygen_mod, "_client", _mock_client(handler))
    resp = client.post("/api/heygen/token")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"] == "sess-123"
    assert body["avatar_id"]


def test_token_missing_key_returns_503(client, monkeypatch):
    monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
    config_module.get_settings.cache_clear()
    resp = client.post("/api/heygen/token")
    assert resp.status_code == 503


def test_token_upstream_error_returns_502(client, monkeypatch):
    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    monkeypatch.setattr(heygen_mod, "_client", _mock_client(handler))
    resp = client.post("/api/heygen/token")
    assert resp.status_code == 502
