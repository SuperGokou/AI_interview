"""面试事件流水(单一职责:把一场面试里发生的每件事按时间记成一行,排查问题用)。

默认关闭;设置 INTERVIEW_TRACE=1 后写到 backend/logs/interview-<id>.log。
只记事件和文字,不记音频和画面本身。文件名以 .log 结尾,已被 git 忽略。
"""

import json
import os
import time
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"


def enabled() -> bool:
    return os.getenv("INTERVIEW_TRACE", "").strip().lower() in ("1", "true", "yes", "on")


class InterviewTrace:
    """Appends one JSON line per event. Never raises: tracing must not break an interview."""

    def __init__(self, session_id: int, *, directory: Path | None = None, active: bool | None = None):
        self._active = enabled() if active is None else active
        self._path = (directory or _LOG_DIR) / f"interview-{session_id}.log"
        self._started = time.monotonic()

    def __call__(self, what: str, **details) -> None:
        if not self._active:
            return
        line = {
            "t": round(time.monotonic() - self._started, 2),
            "clock": time.strftime("%H:%M:%S"),
            "what": what,
            **details,
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as out:
                out.write(json.dumps(line, ensure_ascii=False) + "\n")
        except OSError:
            self._active = False
