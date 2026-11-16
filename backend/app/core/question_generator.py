"""题目生成(单一职责:根据职位描述让文本模型起草带考点、参考答案和追问的面试题)。

客户端可注入(测试传 fake),只需提供 complete(*, system, user, temperature) -> str。
生成结果是草稿:写入题库后由 HR 在后台审阅、修改或删除。
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from app.core.answer_review import TextClient

MAX_GENERATED = 8
MAX_FOLLOW_UPS = 3
DIFFICULTIES = ("初级", "中级", "高级")

_SYSTEM = (
    "你是资深技术面试官,负责为指定职位设计结构化面试题。要求:\n"
    "1. 题目必须紧扣职位描述里的技术栈和职责,不出与职位无关的通用题。\n"
    "2. 知识原理题与实战经历题搭配;实战题要能区分『做过』和『背过』。\n"
    "3. 难度按要求分布,只能取:初级、中级、高级。\n"
    "4. key_points 写 2-4 个判分要点,用分号分隔,说明好答案必须包含什么。\n"
    "5. reference_answer 写一份简明的参考答案(150 字以内)。\n"
    f"6. follow_ups 写 2-{MAX_FOLLOW_UPS} 个追问,必须是只有亲身做过才答得出的细节:"
    "具体数字或规模、遇到过的问题和排查过程、为什么这样选而不是别的方案。\n"
    "7. 不要与【已有题目】重复。题干用口语化的一句话,适合面试官直接念出来。\n"
    "8. 使用指定的语言出题。\n"
    "只输出 JSON,不要多余文字:"
    '{"questions":[{"prompt":"题干","key_points":"要点1;要点2","reference_answer":"参考答案",'
    '"difficulty":"初级|中级|高级","follow_ups":["追问1","追问2"]}]}'
)


@dataclass(frozen=True)
class DraftQuestion:
    prompt: str
    key_points: str
    reference_answer: str
    difficulty: str
    follow_ups: tuple[str, ...]


def _text(value, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _parse(raw: str) -> list[DraftQuestion]:
    s = (raw or "").strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("model did not return a JSON object")
    data = json.loads(s[start : end + 1])
    items = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("model did not return a questions list")
    drafts: list[DraftQuestion] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        prompt = _text(item.get("prompt"), 4000)
        if not prompt:
            continue  # a question without a question is not worth saving
        difficulty = item.get("difficulty")
        raw_follow_ups = item.get("follow_ups")
        candidates = raw_follow_ups if isinstance(raw_follow_ups, list) else []
        follow_ups = tuple(t for t in (_text(f, 500) for f in candidates) if t)[:MAX_FOLLOW_UPS]
        drafts.append(
            DraftQuestion(
                prompt=prompt,
                key_points=_text(item.get("key_points"), 4000),
                reference_answer=_text(item.get("reference_answer"), 8000),
                difficulty=difficulty if difficulty in DIFFICULTIES else "中级",
                follow_ups=follow_ups,
            )
        )
    return drafts


def generate_questions(
    client: TextClient,
    *,
    job_title: str,
    jd: str,
    language: str,
    count: int,
    existing: Sequence[str] = (),
    focus: str = "",
) -> list[DraftQuestion]:
    """Draft up to `count` questions. Raises ValueError when nothing usable comes back."""
    count = max(1, min(count, MAX_GENERATED))
    existing_text = "\n".join(f"- {p}" for p in existing) or "(无)"
    user = (
        f"【职位】{job_title}\n【职位描述】{jd}\n"
        f"【语言】{'English' if language == 'en' else '中文'}\n"
        f"【数量】{count} 道,难度由浅入深\n"
        f"【侧重方向】{focus.strip() or '按职位描述均衡覆盖'}\n"
        f"【已有题目】\n{existing_text}"
    )
    drafts = _parse(client.complete(system=_SYSTEM, user=user, temperature=0.7))
    seen = {p.strip() for p in existing}
    unique: list[DraftQuestion] = []
    for draft in drafts:
        if draft.prompt not in seen:
            seen.add(draft.prompt)
            unique.append(draft)
    if not unique:
        raise ValueError("model returned no usable questions")
    return unique[:count]
