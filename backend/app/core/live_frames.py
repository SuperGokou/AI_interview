"""候选人的最新一帧画面(单一职责:进程内暂存,供监督页实时查看)。

只在内存里放每场面试最新的一帧,不落盘;面试结束即清除,过期的帧不再提供。
多进程部署时监督页必须和面试连到同一个进程(当前是单进程部署)。
"""

import time

# 超过这个时间没有新画面,就当作候选人已关闭摄像头或已离开。
STALE_AFTER_S = 15.0


class LiveFrames:
    def __init__(self, *, stale_after_s: float = STALE_AFTER_S, clock=time.monotonic):
        self._frames: dict[int, tuple[bytes, float]] = {}
        self._stale_after_s = stale_after_s
        self._clock = clock

    def put(self, session_id: int, jpeg: bytes) -> None:
        self._frames[session_id] = (jpeg, self._clock())

    def get(self, session_id: int) -> bytes | None:
        entry = self._frames.get(session_id)
        if entry is None or self._clock() - entry[1] > self._stale_after_s:
            return None
        return entry[0]

    def drop(self, session_id: int) -> None:
        self._frames.pop(session_id, None)


live_frames = LiveFrames()
