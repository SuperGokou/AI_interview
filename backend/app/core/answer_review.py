"""逐题评审(单一职责:用文本模型给每个回答打分并归类,以及生成 AI 参考答案)。

客户端可注入(测试传 fake),只需提供 complete(*, system, user, temperature) -> str。
"""

import json
from collections.abc import Sequence
from typing import Protocol

from app.core.integrity_signals import Turn, TurnScore

REFERENCE_ANSWER_COUNT = 3

_VALID_KINDS = {"main", "probe", "other"}

_SCORE_SYSTEM = (
    "你是资深面试评估官。下面是一场面试中按顺序编号的问答。请对每一题:"
    "1) 判断问题类型 kind:main=题库中的主问题;probe=针对候选人上一个回答的细节追问、"
    "或题库中标为探针的问题;other=寒暄、流程说明等不考察能力的内容。"
    "2) 给候选人的回答打 0-100 的整数分 score,只看内容是否正确、具体、有细节,不看口语是否流畅。"
    "回答『不知道』『不太清楚』或明显答非所问,给低分。"
    '只输出 JSON,不要多余文字:{"turns":[{"index":整数,"kind":"main|probe|other","score":整数}]}'
)

_REFERENCE_SYSTEM = (
    "你在模拟一名直接把面试题丢给 AI 助手、然后照读答案的候选人。"
    f"请针对给出的面试问题,写出 {REFERENCE_ANSWER_COUNT} 份彼此措辞不同、但都是 AI 助手典型风格的口头回答,"
    "每份 150-300 字,使用与问题相同的语言。"
    '只输出 JSON,不要多余文字:{"answers":["...","...","..."]}'
)


class TextClient(Protocol):
    def complete(self, *, system: str, user: str, temperature: float = 0.3) -> str: ...


def _parse_object(raw: str) -> dict:
    s = (raw or "").strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("model did not return a JSON object")
    data = json.loads(s[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("model did not return a JSON object")
    return data


def _format_turns(turns: Sequence[Turn]) -> str:
    return "\n\n".join(f"[{t.index}] 问:{t.question}\n答:{t.answer}" for t in turns)


def _format_bank(questions: Sequence[dict]) -> str:
    lines = [
        f"- {'[探针] ' if q.get('is_probe') else ''}{q.get('prompt', '')}" for q in questions
    ]
    return "\n".join(lines) or "(无)"


def score_turns(
    client: TextClient, turns: Sequence[Turn], questions: Sequence[dict]
) -> list[TurnScore]:
    """One model call for the whole interview. Entries the model gets wrong
    (unknown index, bad kind, out-of-range score) are dropped, not guessed."""
    if not turns:
        return []
    user = f"【题库】\n{_format_bank(questions)}\n\n【问答】\n{_format_turns(turns)}"
    data = _parse_object(client.complete(system=_SCORE_SYSTEM, user=user, temperature=0.0))
    known = {t.index for t in turns}
    scores: dict[int, TurnScore] = {}
    for item in data.get("turns") or []:
        if not isinstance(item, dict):
            continue
        index, kind, score = item.get("index"), item.get("kind"), item.get("score")
        if type(index) is not int or index not in known or kind not in _VALID_KINDS:
            continue
        if type(score) is not int or not 0 <= score <= 100:
            continue
        scores[index] = TurnScore(index=index, kind=kind, score=score)
    return [scores[i] for i in sorted(scores)]


def reference_answers(client: TextClient, question: str) -> list[str]:
    """What an AI assistant would say if handed this question verbatim."""
    data = _parse_object(
        client.complete(system=_REFERENCE_SYSTEM, user=question, temperature=0.8)
    )
    answers = data.get("answers")
    if not isinstance(answers, list):
        raise ValueError("model did not return an answers list")
    return [a.strip() for a in answers if isinstance(a, str) and a.strip()]
