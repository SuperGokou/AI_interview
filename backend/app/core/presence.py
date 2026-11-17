"""监督员是否在线(单一职责:记住每个监督链接最近一次访问的时间)。

监督页每隔几秒拉一次数据,拉到就算在线;停止访问一小段时间后算离线。
只存在进程内存里,不落库。
"""

import time

# 监督页约 2.5 秒轮询一次;留出几次丢包的余量。
ONLINE_WINDOW_S = 10.0


class Presence:
    def __init__(self, *, window_s: float = ONLINE_WINDOW_S, clock=time.monotonic):
        self._seen: dict[int, float] = {}
        self._window_s = window_s
        self._clock = clock

    def seen(self, link_id: int) -> None:
        self._seen[link_id] = self._clock()

    def online(self, link_id: int) -> bool:
        at = self._seen.get(link_id)
        return at is not None and self._clock() - at <= self._window_s


    def clear(self) -> None:
        self._seen.clear()


supervisor_presence = Presence()
