"""候选人长时间不说话时的处理(单一职责:判断面试官什么时候该开口)。纯逻辑,无副作用。

实时模型只在听到人声后才回应,候选人一直沉默它就一直等。真人面试官不会这样:
等一会儿先问一句要不要重复问题,还不说话就进入下一题,连着几题都没人应答就停下来。
"""

from dataclasses import dataclass

CHECK_IN = "check_in"  # 问一句:需要重复问题,还是再想一会儿?
MOVE_ON = "move_on"  # 进入下一题
PAUSE = "pause"  # 连着几题没人应答,说明情况并等待

NUDGE_ZH = {
    CHECK_IN: (
        "候选人已经有一阵没有说话了。用一句话温和地确认一下:是需要你把问题再说一遍,"
        "还是想再考虑一会儿。不要给提示,不要透露答案,不要问新的问题。"
    ),
    MOVE_ON: (
        "候选人仍然没有回答。平静地说一句『没关系,我们先看下一题』,然后问题库里的下一道题;"
        "如果已经是最后一题,就按收尾的方式结束面试。不要评价,不要流露失望。"
    ),
    PAUSE: (
        "候选人已经连续几道题都没有作答,可能是离开了或者设备出了问题。"
        "用一两句话说明:你听不到对方的声音,请对方检查麦克风;你会在这里等,对方准备好后直接说话就可以继续。"
        "不要再问新的问题。"
    ),
}

NUDGE_EN = {
    CHECK_IN: (
        "The candidate has been silent for a while. In one sentence, gently ask whether they would like "
        "the question repeated or a little more time. No hints, no answers, no new question."
    ),
    MOVE_ON: (
        "The candidate still has not answered. Calmly say 'no problem, let us move on' and ask the next "
        "question in the bank; if that was the last one, close the interview. No judgement."
    ),
    PAUSE: (
        "The candidate has not answered several questions in a row and may have left or have a device "
        "problem. In a sentence or two say you cannot hear them, ask them to check their microphone, and "
        "that they can simply speak to continue. Do not ask a new question."
    ),
}


def nudge_text(stage: str, language: str = "zh") -> str:
    return (NUDGE_EN if language == "en" else NUDGE_ZH)[stage]


@dataclass
class SilenceWatch:
    """Decides when the interviewer should break a silence.

    check_in_s: quiet time after the interviewer stops before it checks in.
    move_on_s:  further quiet time after that before it moves to the next question.
    max_skipped: unanswered questions in a row before it stops asking and waits.
    """

    check_in_s: float = 20.0
    move_on_s: float = 25.0
    max_skipped: int = 3

    def __post_init__(self) -> None:
        self._quiet_since: float | None = None  # None until the interviewer has spoken
        self._checked_in = False
        self._skipped = 0
        self._paused = False

    def interviewer_audio(self, seconds: float, now: float) -> None:
        """The interviewer produced audio that will play for `seconds`."""
        start = max(self._quiet_since or now, now)
        self._quiet_since = start + seconds

    def candidate_active(self, now: float) -> None:
        """The candidate started speaking or finished an answer."""
        if self._quiet_since is not None:
            self._quiet_since = max(self._quiet_since, now)
        self._checked_in = False
        self._skipped = 0
        self._paused = False

    def due(self, now: float) -> str | None:
        """What the interviewer should do now, if anything. Each stage fires once."""
        if self._quiet_since is None or self._paused:
            return None
        quiet = now - self._quiet_since
        if not self._checked_in:
            if quiet < self.check_in_s:
                return None
            self._checked_in = True
            self._quiet_since = now
            return CHECK_IN
        if quiet < self.move_on_s:
            return None
        self._checked_in = False
        self._quiet_since = now
        self._skipped += 1
        if self._skipped >= self.max_skipped:
            self._paused = True
            return PAUSE
        return MOVE_ON
