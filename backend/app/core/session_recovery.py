"""启动恢复(单一职责:收尾上次进程退出时还「进行中」的面试)。

面试状态由 WebSocket 处理函数在结束时写回。进程被重启或崩溃时这一步不会执行,
会话就永远停在 active:后台显示一场不存在的进行中面试,那条链接也无法判定为已结束。
应用是单进程的,所以启动时任何 active 会话都必然是遗留的。
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db import models

logger = logging.getLogger(__name__)


def close_orphaned_sessions(db: Session) -> int:
    """Mark leftover active sessions as done; returns how many were closed."""
    orphans = db.query(models.InterviewSession).filter_by(status="active").all()
    now = datetime.now(UTC)
    for session in orphans:
        session.status = "done"
        session.ended_at = session.ended_at or now
    if orphans:
        db.commit()
        logger.warning("closed %d interview(s) left active by a previous run", len(orphans))
    return len(orphans)
