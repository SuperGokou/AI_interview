"""诚信/防作弊信号(单一职责:视觉观测→作弊信号 + 诚信等级计算)。纯函数。"""

from dataclasses import dataclass
from typing import List

# 严重度权重
_SEVERITY_WEIGHT = {"low": 1, "medium": 3, "high": 6}

# 视觉观测 flag → (cheat kind, severity)
_VISION_RULES = {
    "gaze_off_screen": ("gaze_off_screen", "medium"),
    "reading_motion": ("reading_motion", "medium"),
    "multi_person": ("multi_person", "high"),
    "person_absent": ("person_absent", "high"),
    "suspicious_object": ("suspicious_object", "high"),
}


@dataclass(frozen=True)
class CheatSignal:
    kind: str
    severity: str  # low / medium / high
    evidence: str = ""


def interpret_visual_observation(obs: dict) -> List[CheatSignal]:
    """把一次结构化视觉观测解释成作弊信号列表。

    obs 形如 {"flags": ["gaze_off_screen", ...], "detail": "..."};未知 flag 忽略。
    """
    signals: List[CheatSignal] = []
    detail = (obs.get("detail") or "").strip()
    for flag in obs.get("flags", []) or []:
        rule = _VISION_RULES.get(flag)
        if rule:
            kind, severity = rule
            signals.append(CheatSignal(kind=kind, severity=severity, evidence=detail))
    return signals


def compute_integrity_level(events: List) -> str:
    """按累计严重度加权算诚信等级,返回 green / yellow / red。

    events: 带 .severity 属性的对象,或含 'severity' 键的 dict。
    阈值:score>=6 → red;score>=3 → yellow;否则 green。
    """
    score = 0
    for e in events:
        sev = getattr(e, "severity", None)
        if sev is None and isinstance(e, dict):
            sev = e.get("severity")
        score += _SEVERITY_WEIGHT.get(sev, 0)
    if score >= 6:
        return "red"
    if score >= 3:
        return "yellow"
    return "green"
