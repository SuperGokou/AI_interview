"""口型流客户端(单一职责:把面试官语音送到 GPU 口型服务,取回嘴部画面)。

口型是增强项,不是面试的必要条件:连接不上、中途断开或渲染变慢时,这个客户端
只会安静地停用,面试照常进行,浏览器退回到按音量驱动的近似口型。
协议见 deploy/gpu/stream_service.py。
"""

import asyncio
import json
import logging
import struct
from collections.abc import AsyncIterator

import websockets

logger = logging.getLogger(__name__)

_HEADER = struct.Struct("<II")  # utterance id, frame index
_CONNECT_TIMEOUT_S = 4.0


class MouthStream:
    def __init__(self, connection, config: dict):
        self._ws = connection
        self.config = config  # {"fps", "frame": {...}, "patch": {...}}
        self._alive = True
        self._pending_audio = False  # audio sent since the last end/reset

    @classmethod
    async def connect(cls, url: str, api_key: str, sample_rate: int) -> "MouthStream | None":
        """Open a session; None when the service is unreachable, busy or misconfigured."""
        if not url or not api_key:
            return None
        try:
            async with asyncio.timeout(_CONNECT_TIMEOUT_S):
                connection = await websockets.connect(
                    f"{url}?rate={sample_rate}",
                    additional_headers={"Authorization": f"Bearer {api_key}"},
                    max_size=2 * 1024 * 1024,
                    open_timeout=_CONNECT_TIMEOUT_S,
                )
                ready = json.loads(await connection.recv())
        except Exception as exc:  # refused, busy (4429), bad key (4401), timeout...
            logger.warning("lip-sync service unavailable, using audio-driven mouth: %s", exc)
            return None
        if not isinstance(ready, dict) or ready.get("type") != "ready":
            await connection.close()
            return None
        return cls(connection, {k: v for k, v in ready.items() if k != "type"})

    @property
    def alive(self) -> bool:
        return self._alive

    async def _send(self, payload) -> None:
        if not self._alive:
            return
        try:
            await self._ws.send(payload)
        except Exception as exc:
            self._disable(exc)

    def _disable(self, reason) -> None:
        if self._alive:
            self._alive = False
            logger.warning("lip-sync stream stopped, using audio-driven mouth: %s", reason)

    async def send_audio(self, pcm: bytes) -> None:
        self._pending_audio = True
        await self._send(pcm)

    async def end_utterance(self) -> bool:
        """Flush the utterance. Returns False when no audio was sent, in which
        case the service did not start a new utterance either."""
        if not self._pending_audio:
            return False
        self._pending_audio = False
        await self._send(json.dumps({"type": "end"}))
        return True

    async def reset(self) -> None:
        """Drop the utterance being rendered (the reply was cut short)."""
        if self._pending_audio:
            self._pending_audio = False
            await self._send(json.dumps({"type": "reset"}))

    async def frames(self) -> AsyncIterator[bytes]:
        """Yield frame messages (8-byte header + JPEG) exactly as received."""
        try:
            async for message in self._ws:
                if isinstance(message, bytes) and len(message) > _HEADER.size:
                    yield message
        except Exception as exc:
            self._disable(exc)
        else:
            self._disable("closed by the service")

    async def close(self) -> None:
        self._alive = False
        try:
            await self._ws.close()
        except Exception:
            pass
