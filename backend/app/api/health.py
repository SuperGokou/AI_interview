"""健康检查(单一职责:报告 DB 连通与模型 key 配置状态)。"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import get_db

router = APIRouter(prefix="/api")


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok",
        "database": "up" if db_ok else "down",
        "models": {
            "qwen": bool(settings.dashscope_api_key),
            "deepseek": bool(settings.deepseek_api_key),
        },
    }
