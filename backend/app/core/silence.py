"""候选人长时间不说话时的处理(单一职责:判断面试官什么时候该开口)。纯逻辑,无副作用。

实时模型只在听到人声后才回应,候选人一直沉默它就一直等。真人面试官不会这样:
等一会儿先问一句要不要重复问题,还不说话就进入下一题,连着几题都没人应答就停下来。
同一句话不会说第二遍:每次的说法都要求和上一次不同。
"""

from dataclasses import dataclass

CHECK_IN = "check_in"  # 问一句:需要重复问题,还是再想一会儿?
MOVE_ON = "move_on"  # 进入下一题
PAUSE = "pause"  # 连着几题没人应答,说明情况并等待

_VARY_ZH = "这不是第一次遇到沉默了:换一种说法,不要重复你之前说过的原话。"
_VARY_EN = "This is not the first silence: phrase it differently from what you said before."

NUDGE_ZH = {
    CHECK_IN: (
        "候选人听完问题后已经有一阵没有说话,可能在思考,也可能没听清。"
        "像真人面试官那样用一句简短自然的话关心一下,例如问对方是否需要你把问题再说一遍,"
        "或者告诉对方可以先说说大致的思路。直接说这句话本身,不要以『没关系』开头,不要称呼全名。"
        "不要给提示,不要透露答案,不要问新的问题。"
    ),
    MOVE_ON: (
        "候选人仍然没有回答。自然地过渡一句(比如这道题先放一放),然后问题库里的下一道题;"
        "如果已经是最后一题,就按收尾的方式结束面试。不要评价,不要流露失望。"
    ),
    PAUSE: (
        "候选人已经连续几道题都没有作答,可能是离开了或者设备出了问题。"
        "用一两句话说明:你这边听不到对方的声音,请对方检查一下麦克风;你会在这里等,对方准备好后直接说话就可以继续。"
        "不要再问新的问题。"
    ),
}

NUDGE_EN = {
    CHECK_IN: (
        "The candidate has been quiet for a while after your question; they may be thinking or may not "
        "have heard it. In one short natural sentence, ask whether they would like the question repeated, "
        "or invite them to start with a rough outline. No hints, no answers, no new question."
    ),
    MOVE_ON: (
        "The candidate still has not answered. Bridge naturally (for example, park this one for now) and "
        "ask the next question in the bank; if that was the last one, close the interview. No judgement."
    ),
    PAUSE: (
        "The candidate has not answered several questions in a row and may have left or have a device "
        "problem. In a sentence or two say you cannot hear them, ask them to check their microphone, and "
        "that they can simply speak to continue. Do not ask a new question."
    ),
}


def nudge_text(stage: str, language: str = "zh", *, repeated: bool = False) -> str:
    en = language == "en"
    text = (NUDGE_EN if en else NUDGE_ZH)[stage]
    return f"{text}{_VARY_EN if en else _VARY_ZH}" if repeated else text


@dataclass
class SilenceWatch:
    """Decides when the interviewer should break a silence.

    check_in_s: quiet time after the interviewer stops before it checks in.
    move_on_s:  further quiet time after that before it moves to the next question.
    max_skipped: unanswered questions in a row before it stops asking and waits.
    """

    check_in_s: float = 20.0
    move_on_s: float = 30.0
    max_skipped: int = 3

    def __post_init__(self) -> None:
        self._quiet_since: float | None = None  # None until the interviewer has spoken
        self._checked_in = False
        self._skipped = 0
        self._paused = False

    @property
    def repeated(self) -> bool:
        """True once a question has already gone unanswered in this stretch of silence."""
        return self._skipped > 0

    def interviewer_audio(self, seconds: float, now: float) -> None:
        """The interviewer produced audio that will play for `seconds`."""
        start = max(self._quiet_since or now, now)
        self._quiet_since = start + seconds

    def interviewer_speaking(self, now: float, *, margin: float = 0.0) -> bool:
        """Whether audio already sent to the page is still playing there."""
        return self._quiet_since is not None and self._quiet_since + margin > now

    def audible_since(self, since: float, *, margin: float = 0.0) -> bool:
        """Whether the interviewer could be heard at any point from `since` on."""
        return self._quiet_since is not None and self._quiet_since + margin > since

    def cut_short(self, now: float) -> None:
        """Playback was stopped early (the candidate talked over the interviewer)."""
        if self._quiet_since is not None:
            self._quiet_since = min(self._quiet_since, now)

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
