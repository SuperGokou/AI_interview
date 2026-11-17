"""面试中的违规处理(单一职责:某次违规该当场提醒,还是该结束面试)。纯逻辑。

像真人监考一样:看到手机、听到键盘声、发现旁人,先当场提醒;
第 limit 次违规(默认第 3 次)直接结束面试并告知原因。
视线、桌上物品、环境噪音这类需要结合上下文判断的线索只记录,不计入违规。
"""

from dataclasses import dataclass

# 计入违规的类型 → 面试官提醒时怎么描述它。
_WHAT_ZH = {
    "keyboard_typing": "听到了持续的键盘敲击声,本次面试是口头作答,请不要使用键盘",
    "phone": "看到了手机,面试过程中请把手机放到一边,不要查看",
    "multi_person": "画面里出现了其他人,面试需要独立完成,请确保房间里只有你一个人",
    "other_voice": "听到了其他人说话的声音,面试需要独立完成,请确保没有他人在旁边提示",
}
_WHAT_EN = {
    "keyboard_typing": "sustained keyboard typing was heard; this is a spoken interview, so please do not type",
    "phone": "a phone was seen; please put it away and do not look at it",
    "multi_person": "another person appeared on camera; the interview must be done alone",
    "other_voice": "another person's voice was heard; nobody may prompt you during the interview",
}
WARNED_KINDS = frozenset(_WHAT_ZH)

WARN = "warn"
END = "end"

# 终止面试时记一条事件,报告里能看到原因。
TERMINATION_KIND = "repeated_violation"

# 宣布结束后,留给面试官把话说完的时间。
FAREWELL_SECONDS = 12.0

END_NOTICE_ZH = "监考多次检测到违规行为，属于多次违规，本次面试已结束。"
END_NOTICE_EN = "Repeated violations were detected, so this interview has ended."


def _describe(kinds: list[str], table: dict[str, str], joiner: str) -> str:
    return joiner.join(table[k] for k in sorted(set(kinds)) if k in table)


def warning_text(kinds: list[str], count: int, limit: int, language: str = "zh") -> str:
    """What the interviewer is told to say for the count-th violation (count < limit)."""
    final = count >= limit - 1
    if language == "en":
        last = " Make clear that this is the final warning." if final else ""
        return (
            f"The proctoring system just noticed this: {_describe(kinds, _WHAT_EN, '; ')}. "
            "Pause the interview politely and tell the candidate in one or two natural sentences what was "
            f"noticed and what you ask of them. Say that this is violation {count} and that the interview "
            f"ends at violation {limit}.{last} Then pick the current question back up. Stay calm and "
            "matter-of-fact; do not accuse them of cheating."
        )
    last = "明确告诉对方这是最后一次提醒。" if final else ""
    return (
        f"监考系统刚刚发现:{_describe(kinds, _WHAT_ZH, ';')}。"
        "请礼貌地暂停一下,用一两句自然的话向候选人说明发现了什么、希望对方怎么做;"
        f"并说明这是第 {count} 次违规,累计 {limit} 次将直接结束面试。{last}"
        "说完后接着当前的问题继续。语气平和、就事论事,不要指责对方作弊。"
    )


def ending_text(language: str = "zh") -> str:
    if language == "en":
        return (
            "A further violation was detected after the earlier warnings. Tell the candidate calmly, in one "
            "or two sentences, that because of repeated violations the interview ends now and the hiring "
            "team will be informed. Do not ask anything else."
        )
    return (
        "在之前的提醒之后,监考系统再次发现了违规行为。请平静地用一两句话告知候选人:"
        "由于多次违规,本次面试到此结束,情况会如实反馈给招聘方。不要再提问。"
    )


def end_notice(language: str = "zh") -> str:
    return END_NOTICE_EN if language == "en" else END_NOTICE_ZH


@dataclass
class ViolationPolicy:
    """Counts violations: each one before the limit gets a warning, the limit-th ends it."""

    limit: int = 3

    def __post_init__(self) -> None:
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    def record(self, kinds: list[str]) -> str | None:
        """Returns WARN, END, or None when nothing here counts as a violation.

        Several kinds found in the same check count as one violation.
        """
        if self.limit <= 0 or not WARNED_KINDS.intersection(kinds):
            return None
        self._count += 1
        return END if self._count >= self.limit else WARN
