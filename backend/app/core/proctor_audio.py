"""监考用的声音片段(单一职责:攒住最近几秒候选人环境声,打包成模型能听的 WAV)。

浏览器另开一路【不降噪】的麦克风专门给监考用:面试官那一路开着降噪,键盘声会被滤掉。
这里只做纯数据处理,不调用任何模型。
"""

import array
import io
import wave

SAMPLE_RATE = 16_000
_BYTES_PER_SECOND = SAMPLE_RATE * 2  # PCM16 mono

# 低于这个响度就当作安静,不送去分析:省钱,也避免模型对着静音编造声音。
QUIET_RMS = 120.0
# 太短的片段听不出什么。
MIN_SECONDS = 2.0


class AudioWindow:
    """Keeps the most recent few seconds of PCM16 mono audio."""

    def __init__(self, *, max_seconds: float = 12.0):
        self._limit = int(max_seconds * _BYTES_PER_SECOND)
        self._chunks: list[bytes] = []
        self._size = 0

    def append(self, pcm: bytes) -> None:
        if not pcm:
            return
        self._chunks.append(pcm)
        self._size += len(pcm)
        while self._size > self._limit and len(self._chunks) > 1:
            self._size -= len(self._chunks.pop(0))

    def take(self) -> bytes:
        """Return what was collected since the last call and start over."""
        pcm = b"".join(self._chunks)[-self._limit :]
        self._chunks, self._size = [], 0
        return pcm[: len(pcm) - (len(pcm) % 2)]


def rms(pcm: bytes) -> float:
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    picked = samples[::8]  # loudness does not need every sample
    if not picked:
        return 0.0
    return (sum(s * s for s in picked) / len(picked)) ** 0.5


def worth_hearing(pcm: bytes) -> bool:
    return len(pcm) >= MIN_SECONDS * _BYTES_PER_SECOND and rms(pcm) >= QUIET_RMS


def pcm_to_wav(pcm: bytes, *, sample_rate: int = SAMPLE_RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm)
    return buffer.getvalue()
