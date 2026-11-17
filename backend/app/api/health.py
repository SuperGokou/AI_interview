"""健康检查(单一职责:报告 DB 连通与模型 key 配置状态)。"""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Report liveness. Returns 503 when the database is unreachable so that
    container health checks and reverse proxies stop routing to a broken app."""
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.exception("health check: database unreachable")
        db_ok = False
    body = {
        "status": "ok" if db_ok else "degraded",
        "database": "up" if db_ok else "down",
        "models": {
            # Neutral names: this endpoint is public, and the product presents its
            # models as KY-BOT rather than naming the providers behind it.
            "realtime": bool(settings.dashscope_api_key),
            "scoring": bool(settings.deepseek_api_key),
        },
    }
    return JSONResponse(body, status_code=200 if db_ok else 503)
