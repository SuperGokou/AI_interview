"""坤曜面试系统 — 配置(单一职责:从环境变量装配 Settings)。"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录的 .env(从 yzbot 复制而来)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

# Qwen-Omni 该模型有效音色:女声 + 男声
QWEN_VOICES = ["Serena", "Sunny", "Kiki", "Tina", "Ethan", "Dylan", "Peter", "Aiden"]


@dataclass(frozen=True)
class Settings:
    # Qwen-Omni Realtime(DashScope)
    dashscope_api_key: str
    qwen_model: str
    qwen_voice: str
    qwen_ws_url: str
    input_sample_rate: int
    output_sample_rate: int
    vision_fps: float
    # 候选人停顿多久才算说完(毫秒)。太短会在候选人思考时抢话。
    vad_silence_ms: int
    # DeepSeek(OpenAI 兼容)
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    # HeyGen 流式数字人
    heygen_api_key: str
    heygen_avatar_id: str
    heygen_base_url: str
    # 面试官对外身份(产品名与所属公司)
    interviewer_name: str
    interviewer_company: str
    # 实时口型服务(可选;未配置时使用按音量驱动的近似口型)
    mouth_stream_url: str
    mouth_stream_key: str
    mouth_playback_delay_ms: int
    # 画面监考(视觉模型;OpenAI 兼容接口)
    proctor_api_key: str
    proctor_base_url: str
    proctor_model: str
    proctor_interval_s: int
    # 文本向量(AI 答案相似度);OpenAI 兼容接口
    embedding_api_key: str
    embedding_base_url: str
    embedding_model: str
    # 数据库
    database_url: str


def _bounded_int(name: str, default: int, low: int, high: int) -> int:
    """Integer setting clamped to a sane range; a malformed value falls back to the default."""
    try:
        value = int(os.getenv(name, "") or default)
    except ValueError:
        return default
    return max(low, min(high, value))


@lru_cache
def get_settings() -> Settings:
    # DASHSCOPE_API_KEY 为规范名,QWEN_API_KEY 为别名(yzbot .env 用的是后者)
    dashscope_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY", "")
    voice = os.getenv("QWEN_OMNI_VOICE", "Tina")
    if voice not in QWEN_VOICES:
        voice = "Tina"
    default_db = f"sqlite:///{BASE_DIR / 'backend' / 'interviewai.db'}"
    return Settings(
        dashscope_api_key=dashscope_key,
        qwen_model=os.getenv("QWEN_OMNI_MODEL", "qwen3.8-omni-flash-realtime"),
        qwen_voice=voice,
        qwen_ws_url=os.getenv(
            "QWEN_OMNI_WS_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
        ),
        input_sample_rate=int(os.getenv("QWEN_INPUT_SR", "16000")),
        output_sample_rate=int(os.getenv("QWEN_OUTPUT_SR", "24000")),
        vision_fps=float(os.getenv("QWEN_VISION_FPS", "1.5")),
        vad_silence_ms=_bounded_int("QWEN_VAD_SILENCE_MS", 1600, 300, 5000),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        heygen_api_key=os.getenv("HEYGEN_API_KEY", ""),
        heygen_avatar_id=os.getenv("HEYGEN_AVATAR_ID", "Anna_public_3_20240108"),
        heygen_base_url=os.getenv("HEYGEN_BASE_URL", "https://api.heygen.com"),
        interviewer_name=os.getenv("INTERVIEWER_NAME", "").strip() or "KY-BOT",
        interviewer_company=os.getenv("INTERVIEWER_COMPANY", "").strip()
        or "江苏坤曜智能科技有限公司",
        mouth_stream_url=os.getenv("MOUTH_STREAM_URL", "").strip(),
        mouth_stream_key=os.getenv("MOUTH_STREAM_KEY", "").strip(),
        mouth_playback_delay_ms=_bounded_int("MOUTH_PLAYBACK_DELAY_MS", 450, 0, 2000),
        proctor_api_key=os.getenv("PROCTOR_API_KEY") or dashscope_key,
        proctor_base_url=os.getenv(
            "PROCTOR_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        # 可填多个,逗号分隔,按顺序尝试:不同账号/地域开通的模型不同。
        proctor_model=os.getenv("PROCTOR_MODEL", "qwen3.8-flash,qwen3-vl-plus,qwen-vl-plus"),
        # 0 关闭画面监考。
        proctor_interval_s=_bounded_int("PROCTOR_INTERVAL_S", 8, 0, 600),
        # 默认复用百炼的 key;也可指向自建的开源向量模型服务(如 bge-m3)。
        embedding_api_key=os.getenv("EMBEDDING_API_KEY") or dashscope_key,
        embedding_base_url=os.getenv(
            "EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-v3"),
        database_url=os.getenv("DATABASE_URL", default_db),
    )
