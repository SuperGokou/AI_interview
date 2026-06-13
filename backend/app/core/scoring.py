"""面试评分(单一职责:用 DeepSeek 把转写+题库+JD+作弊摘要生成结构化报告)。

DeepSeek 客户端可注入(测试传 fake),离线可测。
"""

import json
from typing import List, Optional

from app.core.deepseek_client import DeepSeekClient

_SYSTEM = (
    "你是资深面试评估官。基于【职位/JD】【题库(含考点/标答/难度)】【面试转写】【作弊检测摘要】,"
    "给候选人打分并写评估。难题占分更高。分数 0-100 整数。"
    "只输出 JSON,不要多余文字:"
    '{"score_professional":整数,"score_communication":整数,"score_job_match":整数,'
    '"score_demeanor":整数或null,"ai_risk_level":"low"或"medium"或"high",'
    '"feedback":"分维度评语","overall":"录用倾向+亮点+顾虑"}'
)

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


def _int_or_none(v):
    return None if v is None else int(v)


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
        raw = self._client.complete(system=_SYSTEM, user=user, temperature=0.2)
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> dict:
        try:
            data = json.loads(_extract_json(raw))
            return {
                "score_professional": _int_or_none(data.get("score_professional")),
                "score_communication": _int_or_none(data.get("score_communication")),
                "score_job_match": _int_or_none(data.get("score_job_match")),
                "score_demeanor": _int_or_none(data.get("score_demeanor")),
                "ai_risk_level": data.get("ai_risk_level"),
                "feedback": str(data.get("feedback", "")),
                "overall": str(data.get("overall", "")),
            }
        except Exception:
            return dict(_SAFE_DEFAULT)
