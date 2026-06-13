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


def list_cheat_events(db: Session, session_id: int) -> List[models.CheatEvent]:
    return (
        db.query(models.CheatEvent)
        .filter_by(session_id=session_id)
        .order_by(models.CheatEvent.id)
        .all()
    )


def integrity_level(db: Session, session_id: int) -> str:
    return compute_integrity_level(list_cheat_events(db, session_id))
