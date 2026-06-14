"""菜鸟庆面试系统 — 配置(单一职责:从环境变量装配 Settings)。"""

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
    # DeepSeek(OpenAI 兼容)
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    # HeyGen 流式数字人
    heygen_api_key: str
    heygen_avatar_id: str
    heygen_base_url: str
    # 数据库
    database_url: str


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
        qwen_model=os.getenv("QWEN_OMNI_MODEL", "qwen3.5-omni-plus-realtime"),
        qwen_voice=voice,
        qwen_ws_url=os.getenv(
            "QWEN_OMNI_WS_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
        ),
        input_sample_rate=int(os.getenv("QWEN_INPUT_SR", "16000")),
        output_sample_rate=int(os.getenv("QWEN_OUTPUT_SR", "24000")),
        vision_fps=float(os.getenv("QWEN_VISION_FPS", "1.5")),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        heygen_api_key=os.getenv("HEYGEN_API_KEY", ""),
        heygen_avatar_id=os.getenv("HEYGEN_AVATAR_ID", "Anna_public_3_20240108"),
        heygen_base_url=os.getenv("HEYGEN_BASE_URL", "https://api.heygen.com"),
        database_url=os.getenv("DATABASE_URL", default_db),
    )
