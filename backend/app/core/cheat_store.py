"""作弊事件落库与查询(单一职责:cheat_events 读写 + 当前诚信等级)。"""

from typing import List

from sqlalchemy.orm import Session

from app.core.integrity import compute_integrity_level
from app.db import models


def record_cheat_event(
    db: Session, session_id: int, *, kind: str, severity: str, evidence: str = ""
) -> models.CheatEvent:
    ev = models.CheatEvent(
        session_id=session_id, kind=kind, severity=severity, evidence=evidence
    )
    db.add(ev)
    db.commit()
    return ev


# 画面由浏览器缩小后上传,正常只有几十 KB;异常大的不存。
MAX_SNAPSHOT_BYTES = 400 * 1024


def save_snapshot(db: Session, event: models.CheatEvent, jpeg: bytes) -> bool:
    """Keep the frame a finding was based on. Returns False when it was not stored."""
    if not jpeg or len(jpeg) > MAX_SNAPSHOT_BYTES:
        return False
    db.add(models.EventSnapshot(event_id=event.id, session_id=event.session_id, jpeg=jpeg))
    db.commit()
    return True


def get_snapshot(db: Session, session_id: int, event_id: int) -> bytes | None:
    row = (
        db.query(models.EventSnapshot)
        .filter_by(session_id=session_id, event_id=event_id)
        .first()
    )
    return row.jpeg if row else None


def events_with_snapshot(db: Session, session_id: int) -> set[int]:
    rows = db.query(models.EventSnapshot.event_id).filter_by(session_id=session_id).all()
    return {event_id for (event_id,) in rows}


def list_cheat_events(db: Session, session_id: int) -> List[models.CheatEvent]:
    return (
        db.query(models.CheatEvent)
        .filter_by(session_id=session_id)
        .order_by(models.CheatEvent.id)
        .all()
    )


def integrity_level(db: Session, session_id: int) -> str:
    return compute_integrity_level(list_cheat_events(db, session_id))
