"""面试中的违规处理(单一职责:某类违规该当场提醒,还是该结束面试)。纯逻辑。

目前只对键盘敲击声这样处理:面试是口头回答,不需要打字。
提醒满 limit 次后再出现一次,就结束面试并告知原因。
"""

from dataclasses import dataclass

# 会被当场提醒、累计后终止面试的违规类型。
WARNED_KINDS = frozenset({"keyboard_typing"})

WARN = "warn"
END = "end"

# 终止面试时记一条事件,报告里能看到原因。
TERMINATION_KIND = "repeated_violation"

# 宣布结束后,留给面试官把话说完的时间。
FAREWELL_SECONDS = 12.0

END_NOTICE_ZH = "监考多次检测到键盘敲击声，属于多次违规，本次面试已结束。"
END_NOTICE_EN = "Typing was detected repeatedly. Because of repeated violations this interview has ended."


def warning_text(count: int, limit: int, language: str = "zh") -> str:
    """What the interviewer is told to say for the count-th warning."""
    if language == "en":
        last = " Make clear this is the final warning." if count >= limit else ""
        return (
            "The proctoring system just heard sustained keyboard typing from the candidate. "
            f"Interrupt politely and say, in one or two sentences, that typing was detected, that this "
            f"is a spoken interview and the keyboard must not be used, and that this is warning "
            f"{count} of {limit}; one more after the last warning ends the interview.{last} "
            "Then continue with the current question. Do not accuse them of cheating."
        )
    last = "明确说明这是最后一次提醒。" if count >= limit else ""
    return (
        "监考系统刚刚检测到候选人那边有持续的键盘敲击声。请礼貌地打断,用一两句话说明:"
        "检测到了键盘敲击声,本次面试是口头作答,面试过程中请不要使用键盘;"
        f"这是第 {count} 次提醒,累计超过 {limit} 次将直接结束面试。{last}"
        "说完后继续当前的问题。不要指责对方作弊。"
    )


def ending_text(language: str = "zh") -> str:
    if language == "en":
        return (
            "Keyboard typing was detected again after repeated warnings. Tell the candidate, calmly and in "
            "one or two sentences, that because of repeated violations the interview ends now and the "
            "hiring team will be informed. Do not ask anything else."
        )
    return (
        "多次提醒之后,监考系统再次检测到键盘敲击声。请平静地用一两句话告知候选人:"
        "由于多次违规,本次面试到此结束,情况会如实反馈给招聘方。不要再提问。"
    )


def end_notice(language: str = "zh") -> str:
    return END_NOTICE_EN if language == "en" else END_NOTICE_ZH


@dataclass
class ViolationPolicy:
    """Counts warned violations: the first `limit` get a warning, the next ends it."""

    limit: int = 3

    def __post_init__(self) -> None:
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    def record(self, kinds: list[str]) -> str | None:
        """Returns WARN, END, or None when nothing here calls for action."""
        if self.limit <= 0 or not WARNED_KINDS.intersection(kinds):
            return None
        self._count += 1
        return END if self._count > self.limit else WARN
