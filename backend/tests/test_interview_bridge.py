import asyncio

import pytest

from app.core.interview_bridge import InterviewBridge


class FakeConversation:
    """记录调用并暴露回调,用于在测试里模拟 SDK 事件。"""

    def __init__(self, *, model, callback, url, api_key=""):
        self.callback = callback
        self.updated = None
        self.connected = False

    def connect(self):
        self.connected = True

    def update_session(self, **kwargs):
        self.updated = kwargs

    def append_audio(self, b64):
        self.last_audio = b64

    def close(self):
        self.connected = False


@pytest.mark.asyncio
async def test_bridge_connects_and_injects_instructions_and_voice():
    captured = {}

    def factory(*, model, callback, url, api_key=""):
        conv = FakeConversation(model=model, callback=callback, url=url, api_key=api_key)
        captured["conv"] = conv
        return conv

    bridge = InterviewBridge(
        conversation_factory=factory, model="m", url="ws://x",
        voice="Ethan", instructions="你是面试官", api_key="k",
    )
    await bridge.connect()
    conv = captured["conv"]
    assert conv.connected is True
    assert conv.updated["voice"] == "Ethan"
    assert conv.updated["instructions"] == "你是面试官"


@pytest.mark.asyncio
async def test_bridge_emits_normalized_audio_event():
    import base64

    def factory(*, model, callback, url, api_key=""):
        return FakeConversation(model=model, callback=callback, url=url, api_key=api_key)

    bridge = InterviewBridge(
        conversation_factory=factory, model="m", url="ws://x",
        voice="Tina", instructions="i",
    )
    await bridge.connect()
    raw = b"\x01\x02\x03"
    bridge._handle_event({"type": "response.audio.delta",
                          "delta": base64.b64encode(raw).decode()})
    event = await asyncio.wait_for(bridge.events(), timeout=1.0)
    assert event == {"kind": "audio", "data": raw}


@pytest.mark.asyncio
async def test_bridge_emits_transcript_delta_live():
    """transcript_delta events are forwarded immediately (not buffered until done)."""

    def factory(*, model, callback, url, api_key=""):
        return FakeConversation(model=model, callback=callback, url=url, api_key=api_key)

    bridge = InterviewBridge(
        conversation_factory=factory, model="m", url="ws://x",
        voice="Tina", instructions="i",
    )
    await bridge.connect()
    bridge._handle_event({"type": "response.audio_transcript.delta", "delta": "Hello "})
    bridge._handle_event({"type": "response.audio_transcript.delta", "delta": "world"})
    delta1 = await asyncio.wait_for(bridge.events(), timeout=1.0)
    delta2 = await asyncio.wait_for(bridge.events(), timeout=1.0)
    assert delta1 == {"kind": "transcript_delta", "text": "Hello "}
    assert delta2 == {"kind": "transcript_delta", "text": "world"}
    # Buffer is still accumulated for the final flush
    assert bridge._transcript_buffer == "Hello world"


@pytest.mark.asyncio
async def test_bridge_send_audio_base64_encodes_pcm():
    import base64

    captured = {}

    def factory(*, model, callback, url, api_key=""):
        conv = FakeConversation(model=model, callback=callback, url=url, api_key=api_key)
        captured["conv"] = conv
        return conv

    bridge = InterviewBridge(
        conversation_factory=factory, model="m", url="ws://x",
        voice="Tina", instructions="i",
    )
    await bridge.connect()
    await bridge.send_audio(b"\x10\x20\x30")
    assert captured["conv"].last_audio == base64.b64encode(b"\x10\x20\x30").decode()
