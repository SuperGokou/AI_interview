"""回答延迟计时(单一职责:估算「面试官说完」到「候选人开口」之间的秒数)。纯逻辑,无 I/O。

面试官音频由模型以快于实时的速度下发,浏览器按顺序连续播放。因此:
    播放结束时刻 ≈ 首个音频分片到达时刻 + 本轮音频总时长
这个估算完全在服务端完成,不依赖浏览器上报,候选人无法通过改前端来伪造。
"""

from dataclasses import dataclass

_BYTES_PER_SAMPLE = 2  # PCM16 mono


@dataclass(frozen=True)
class TurnTiming:
    latency_ms: int | None  # None: 本轮没有可用的计时信息


class TurnTimer:
    def __init__(self, *, sample_rate: int):
        self._bytes_per_second = sample_rate * _BYTES_PER_SAMPLE
        self._audio_started_at: float | None = None
        self._audio_bytes = 0
        self._pending_latency_ms: int | None = None

    def on_interviewer_audio(self, nbytes: int, now: float) -> None:
        if self._audio_started_at is None:
            self._audio_started_at = now
        self._audio_bytes += nbytes

    def on_candidate_speech_started(self, now: float) -> None:
        """Measure at the onset: the question's audio has fully arrived by then.

        Later onsets with no interviewer audio in between are pauses inside the
        same answer and are ignored. Barge-in counts as zero delay.
        """
        if self._audio_started_at is None:
            return
        playback_end = self._audio_started_at + self._audio_bytes / self._bytes_per_second
        self._pending_latency_ms = max(0, round((now - playback_end) * 1000))
        self._audio_started_at = None
        self._audio_bytes = 0

    def on_candidate_transcript(self) -> TurnTiming:
        """Attach the measured latency to the first transcript of the answer.

        The transcript often arrives after the interviewer has already started
        the next reply, so the measurement is held until it is claimed here.
        """
        timing = TurnTiming(latency_ms=self._pending_latency_ms)
        self._pending_latency_ms = None
        return timing
