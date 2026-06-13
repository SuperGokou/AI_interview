"""InterviewBridge — 一个浏览器面试会话 ↔ Qwen-Omni Realtime 的桥接。

借鉴 yzbot OmniBridge:
- conversation_factory 可注入(默认用真实 SDK;测试传 Fake)。
- SDK 回调在自身线程触发,经 loop.call_soon_threadsafe 投递到 asyncio.Queue。
归一化事件:
- {"kind": "audio", "data": <pcm bytes>}        面试官语音(PCM16 24kHz)
- {"kind": "transcript", "text": <str>}         面试官文字转写
- {"kind": "user_transcript", "text": <str>}    候选人语音转写(SDK 支持时)
- {"kind": "close"}                              会话关闭
"""

import asyncio
import base64
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:  # 真实 SDK;离线/CI 环境可能缺失
    from dashscope.audio.qwen_omni import (
        OmniRealtimeConversation,
        OmniRealtimeCallback,
        MultiModality,
    )

    _SDK_AVAILABLE = True
except Exception:  # pragma: no cover
    OmniRealtimeConversation = None  # type: ignore

    class OmniRealtimeCallback:  # type: ignore
        def on_open(self): ...
        def on_close(self, close_status_code=None, close_msg=None): ...
        def on_event(self, message): ...

    class MultiModality:  # type: ignore
        AUDIO = "audio"
        TEXT = "text"

    _SDK_AVAILABLE = False

_EVT_AUDIO_DELTA = "response.audio.delta"
_EVT_TRANSCRIPT_DELTA = "response.audio_transcript.delta"
_EVT_TRANSCRIPT_DONE = "response.audio_transcript.done"
_EVT_RESPONSE_DONE = "response.done"
_EVT_USER_TRANSCRIPT = "conversation.item.input_audio_transcription.completed"


def _default_factory(model: str, callback, url: str, api_key: str = ""):
    if OmniRealtimeConversation is None:  # pragma: no cover
        raise RuntimeError("dashscope qwen_omni SDK 不可用;请注入 conversation_factory。")
    clean_url = url.split("?", 1)[0] if url else url
    return OmniRealtimeConversation(
        model=model, callback=callback, url=clean_url, api_key=api_key or None
    )


class InterviewBridge:
    def __init__(
        self,
        *,
        conversation_factory: Optional[Callable] = None,
        model: str,
        url: str,
        voice: str,
        instructions: str,
        api_key: str = "",
    ):
        self._factory = conversation_factory or _default_factory
        self._model = model
        self._url = url
        self._voice = voice
        self._instructions = instructions
        self._api_key = api_key
        self._queue: asyncio.Queue = asyncio.Queue()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._conv = None
        self._transcript_buffer: str = ""

    def _emit(self, item: dict) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, item)

    def _flush_transcript(self) -> None:
        text = self._transcript_buffer
        self._transcript_buffer = ""
        if text:
            self._emit({"kind": "transcript", "text": text})

    def _handle_event(self, message) -> None:
        if not isinstance(message, dict):
            return
        event_type = message.get("type")
        if event_type == _EVT_AUDIO_DELTA:
            delta = message.get("delta")
            if delta:
                self._emit({"kind": "audio", "data": base64.b64decode(delta)})
        elif event_type == _EVT_TRANSCRIPT_DELTA:
            self._transcript_buffer += message.get("delta", "") or ""
        elif event_type in (_EVT_TRANSCRIPT_DONE, _EVT_RESPONSE_DONE):
            self._flush_transcript()
        elif event_type == _EVT_USER_TRANSCRIPT:
            self._emit({"kind": "user_transcript", "text": message.get("transcript", "")})

    async def connect(self) -> None:
        self._loop = asyncio.get_running_loop()
        bridge = self

        class _CB(OmniRealtimeCallback):
            def on_open(self):
                pass

            def on_close(self, close_status_code=None, close_msg=None):
                bridge._emit({"kind": "close"})

            def on_event(self, message):
                bridge._handle_event(message)

        self._conv = self._factory(
            model=self._model, callback=_CB(), url=self._url, api_key=self._api_key
        )
        self._conv.connect()
        self._conv.update_session(
            output_modalities=[MultiModality.AUDIO, MultiModality.TEXT],
            voice=self._voice,
            instructions=self._instructions,
        )

    async def trigger_response(self, instructions: str = "") -> None:
        create = getattr(self._conv, "create_response", None)
        if callable(create):
            create(instructions=instructions or None)

    async def send_audio(self, pcm: bytes) -> None:
        self._conv.append_audio(base64.b64encode(pcm).decode())

    async def send_image(self, jpeg: bytes) -> None:
        b64 = base64.b64encode(jpeg).decode()
        for name in ("append_video", "append_image", "append_video_frame"):
            method = getattr(self._conv, name, None)
            if callable(method):
                method(b64)
                return
        logger.warning("InterviewBridge: 找不到图像上行方法,丢弃 %d 字节帧。", len(jpeg))

    async def events(self) -> dict:
        return await self._queue.get()

    async def close(self) -> None:
        if self._conv is not None and hasattr(self._conv, "close"):
            self._conv.close()
