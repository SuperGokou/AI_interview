"""面试评分(单一职责:用 DeepSeek 把转写+题库+JD+作弊摘要生成结构化报告)。

DeepSeek 客户端可注入(测试传 fake),离线可测。
"""

import json
from typing import List, Optional

from app.core.deepseek_client import DeepSeekClient

_SYSTEM = (
    "你是资深面试评估官。基于【职位/JD】【题库(含考点/标答/难度)】【面试转写】【作弊检测摘要】,"
    "给候选人打分并写评估。难题占分更高。分数 0-100 整数。"
    "当前评估仅有文字转写，没有可供评估的影像；score_demeanor 必须为 null，评语不得推断表情、目光、姿态。作弊信号仅供人工复核，不代表作弊事实。"
    "只输出 JSON,不要多余文字:"
    '{"score_professional":整数,"score_communication":整数,"score_job_match":整数,'
    '"score_demeanor":整数或null,"ai_risk_level":"low"或"medium"或"high",'
    '"feedback":"分维度评语","overall":"录用倾向+亮点+顾虑"}'
)

_VALID_RISK = {"low", "medium", "high"}

_SAFE_DEFAULT = {
    "score_professional": None,
    "score_communication": None,
    "score_job_match": None,
    "score_demeanor": None,
    "ai_risk_level": None,
    "feedback": "",
    "overall": "评分解析失败",
}

_ROLE_ZH = {"interviewer": "面试官", "candidate": "候选人"}


def _extract_json(raw: str) -> str:
    s = (raw or "").strip()
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return s[start : end + 1]
    return s


def _fmt_questions(questions: List[dict]) -> str:
    lines = []
    for i, q in enumerate(questions, 1):
        lines.append(
            f"{i}.[{q.get('difficulty', '')}] {q.get('prompt', '')} "
            f"| 考点:{q.get('key_points', '')} | 标答:{q.get('reference_answer', '')}"
        )
    return "\n".join(lines)


def _fmt_transcripts(transcripts: List[dict]) -> str:
    return "\n".join(
        f"{_ROLE_ZH.get(t.get('role'), t.get('role', ''))}: {t.get('text', '')}"
        for t in transcripts
    )


def _score(value) -> int | None:
    """0-100 as an int; tolerates '82', 82.0 and 82.4, rejects anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if not isinstance(value, (int, float)) or value != value:  # NaN
        return None
    return round(value) if 0 <= value <= 100 else None


def _text(value) -> str:
    """Plain text from a string, or from the object/list the model sometimes returns."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return "\n".join(f"{k}：{_text(v)}" for k, v in value.items() if _text(v))
    if isinstance(value, list):
        return "\n".join(t for t in (_text(v) for v in value) if t)
    return ""


def _int_or_none(v):
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


class ReportGenerator:
    def __init__(self, client: Optional[object] = None):
        # client 仅需 complete(*, system, user, temperature) -> str
        self._client = client or DeepSeekClient()

    def generate(
        self,
        *,
        job_title: str,
        jd: str,
        transcripts: List[dict],
        questions: List[dict],
        cheat_summary: str = "",
    ) -> dict:
        user = (
            f"【职位】{job_title}\n【JD】{jd}\n\n"
            f"【题库】\n{_fmt_questions(questions)}\n\n"
            f"【面试转写】\n{_fmt_transcripts(transcripts)}\n\n"
            f"【作弊检测摘要】{cheat_summary or '无'}"
        )
        for attempt in range(3):
            raw = self._client.complete(system=_SYSTEM, user=user, temperature=0.2)
            result = self._parse(raw)
            if result != _SAFE_DEFAULT:
                return result
            user += "\n上次输出无法解析。请重新输出完整、有效的 JSON 对象，不要省略字段。"
        raise ValueError("报告生成失败：模型未返回有效 JSON，请重试。")

    @staticmethod
    def _parse(raw: str) -> dict:
        """Accept what the model reliably gets right and repair what it often does not.

        The three scores and the risk level are required. The two text fields are
        not: the model regularly drops one of them or returns the per-dimension
        feedback as an object, and losing a whole interview's report over that is
        worse than a report with one empty paragraph.
        """
        try:
            data = json.loads(_extract_json(raw))
        except ValueError:
            return dict(_SAFE_DEFAULT)
        if not isinstance(data, dict):
            return dict(_SAFE_DEFAULT)
        scores = {
            field: _score(data.get(field))
            for field in ("score_professional", "score_communication", "score_job_match")
        }
        if any(value is None for value in scores.values()):
            return dict(_SAFE_DEFAULT)
        risk = data.get("ai_risk_level")
        if risk not in _VALID_RISK:
            return dict(_SAFE_DEFAULT)
        feedback, overall = _text(data.get("feedback")), _text(data.get("overall"))
        if not feedback and not overall:
            return dict(_SAFE_DEFAULT)
        return {
            **scores,
            "score_demeanor": None,
            "ai_risk_level": risk,
            "feedback": feedback,
            "overall": overall,
        }
