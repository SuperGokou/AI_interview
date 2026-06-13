import importlib

import app.config as config_module


def _fresh_settings(monkeypatch, **env):
    """Reload config with a controlled environment and return fresh Settings."""
    for key in ("QWEN_API_KEY", "DASHSCOPE_API_KEY", "DEEPSEEK_API_KEY",
                "QWEN_OMNI_VOICE", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    importlib.reload(config_module)
    return config_module.get_settings()


def test_qwen_key_reads_qwen_api_key_alias(monkeypatch):
    s = _fresh_settings(monkeypatch, QWEN_API_KEY="sk-qwen")
    assert s.dashscope_api_key == "sk-qwen"


def test_deepseek_key_and_defaults(monkeypatch):
    s = _fresh_settings(monkeypatch, DEEPSEEK_API_KEY="sk-deep")
    assert s.deepseek_api_key == "sk-deep"
    assert s.deepseek_base_url == "https://api.deepseek.com"
    assert s.deepseek_model == "deepseek-chat"


def test_default_voice_is_valid(monkeypatch):
    s = _fresh_settings(monkeypatch)
    assert s.qwen_voice in config_module.QWEN_VOICES


def test_database_url_default_is_sqlite(monkeypatch):
    s = _fresh_settings(monkeypatch)
    assert s.database_url.startswith("sqlite")
