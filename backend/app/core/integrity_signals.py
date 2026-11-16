"""面试后诚信信号(单一职责:把逐题数据解释成可复核的信号)。纯函数,无 I/O。

三类信号都只是「提示人工复核」的线索,不是作弊结论:
- latency_pattern  每次都先停顿差不多长的时间,再给出很长的回答
- probe_gap        主问题答得很好,追问细节却明显答不上来
- ai_similarity    回答与 AI 对同一问题生成的答案高度相似
"""

from collections.abc import Sequence
from dataclasses import dataclass
from math import sqrt
from statistics import median, pstdev

from app.core.integrity import CheatSignal

# 只分析有实质内容的回答;寒暄和一句话回答不携带信号。
SUBSTANTIVE_CHARS = 60

# latency_pattern
LATENCY_MIN_ANSWERS = 3
LATENCY_MEDIAN_S = 4.0  # 中位停顿至少这么长
LATENCY_SPREAD_S = 1.5  # 且各题之间波动不超过这个值

# probe_gap
PROBE_MAIN_SCORE = 75  # 主问题平均分至少这么高
PROBE_GAP = 30  # 且比追问平均分高出这么多

# ai_similarity:候选人回答与 AI 参考答案的相似度,除以 AI 参考答案彼此之间的相似度。
# 接近 1 表示「这段回答像 AI 的程度,和 AI 自己的两份答案彼此相像的程度差不多」。
# 用比值而不是绝对阈值,是因为不同向量模型的余弦值分布差别很大。
SIMILARITY_RATIO = 0.97
SIMILARITY_HIGH_COUNT = 3  # 这么多道题同时命中时,严重度升为 high

_EXCERPT_CHARS = 40


@dataclass(frozen=True)
class Turn:
    """One question and the candidate's (merged) answer to it."""

    index: int  # 1-based, in interview order
    question: str
    answer: str
    latency_ms: int | None = None

    @property
    def substantive(self) -> bool:
        return len(self.answer) >= SUBSTANTIVE_CHARS


@dataclass(frozen=True)
class TurnScore:
    index: int
    kind: str  # "main" | "probe" | "other"
    score: int  # 0-100


@dataclass(frozen=True)
class TurnSimilarity:
    index: int
    ratio: float  # candidate-vs-reference similarity / reference-vs-reference similarity


def build_turns(rows: Sequence[tuple[str, str, int | None]]) -> list[Turn]:
    """Pair each run of candidate utterances with the interviewer text before it.

    rows: (role, text, latency_ms) in interview order. Speech recognition may split
    one answer into several utterances; they are merged, keeping the first latency.
    """
    turns: list[Turn] = []
    question_parts: list[str] = []
    answer_parts: list[str] = []
    latency: int | None = None

    def close_turn() -> None:
        turns.append(
            Turn(
                index=len(turns) + 1,
                question="".join(question_parts),
                answer="".join(answer_parts),
                latency_ms=latency,
            )
        )

    for role, text, latency_ms in rows:
        text = text.strip()
        if role == "candidate":
            if not answer_parts:
                latency = latency_ms
            answer_parts.append(text)
        elif answer_parts:  # the interviewer speaks again: previous turn is complete
            close_turn()
            question_parts, answer_parts, latency = [text], [], None
        else:  # consecutive interviewer utterances form one question
            question_parts.append(text)
    if answer_parts:
        close_turn()
    return turns


def _excerpt(text: str) -> str:
    return text if len(text) <= _EXCERPT_CHARS else f"{text[:_EXCERPT_CHARS]}…"


def latency_signal(turns: Sequence[Turn]) -> CheatSignal | None:
    timed = [t for t in turns if t.substantive and t.latency_ms is not None]
    if len(timed) < LATENCY_MIN_ANSWERS:
        return None
    seconds = [t.latency_ms / 1000 for t in timed]
    mid, spread = median(seconds), pstdev(seconds)
    if mid < LATENCY_MEDIAN_S or spread > LATENCY_SPREAD_S:
        return None
    per_turn = "、".join(f"第{t.index}题 {t.latency_ms / 1000:.1f}s" for t in timed)
    return CheatSignal(
        kind="latency_pattern",
        severity="medium",
        evidence=(
            f"{len(timed)} 个长回答开口前的停顿很一致:中位 {mid:.1f}s,波动 {spread:.1f}s"
            f"(阈值:中位≥{LATENCY_MEDIAN_S:.0f}s 且波动≤{LATENCY_SPREAD_S}s)。{per_turn}。"
            "先固定停顿再流畅作答,可能是在等待并照读外部生成的内容;也可能只是习惯先思考,需结合录像复核。"
        ),
    )


def probe_gap_signal(turns: Sequence[Turn], scores: Sequence[TurnScore]) -> CheatSignal | None:
    main = [s for s in scores if s.kind == "main"]
    probes = [s for s in scores if s.kind == "probe"]
    if not main or not probes:
        return None
    main_avg = sum(s.score for s in main) / len(main)
    probe_avg = sum(s.score for s in probes) / len(probes)
    gap = main_avg - probe_avg
    if main_avg < PROBE_MAIN_SCORE or gap < PROBE_GAP:
        return None
    by_index = {t.index: t for t in turns}
    weakest = sorted(probes, key=lambda s: s.score)[:3]
    details = ";".join(
        f"第{s.index}题「{_excerpt(by_index[s.index].question)}」{s.score}分"
        for s in weakest
        if s.index in by_index
    )
    return CheatSignal(
        kind="probe_gap",
        severity="high" if len(probes) >= 2 else "medium",
        evidence=(
            f"主问题平均 {main_avg:.0f} 分({len(main)} 题),追问平均 {probe_avg:.0f} 分({len(probes)} 题),"
            f"落差 {gap:.0f} 分(阈值:主问题≥{PROBE_MAIN_SCORE} 且落差≥{PROBE_GAP})。"
            f"得分最低的追问:{details}。"
            "主问题表现好但追问细节答不上,可能主问题的回答并非出自本人理解。"
        ),
    )


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = sqrt(sum(x * x for x in a)) * sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def similarity_ratio(
    answer: Sequence[float], references: Sequence[Sequence[float]]
) -> float | None:
    """How close the answer sits to the AI references, relative to how close they
    sit to each other. None when there are too few references to calibrate."""
    if len(references) < 2:
        return None
    to_refs = sum(cosine(answer, r) for r in references) / len(references)
    pairs = [
        cosine(references[i], references[j])
        for i in range(len(references))
        for j in range(i + 1, len(references))
    ]
    among_refs = sum(pairs) / len(pairs)
    return to_refs / among_refs if among_refs > 0 else None


def similarity_signal(
    turns: Sequence[Turn], similarities: Sequence[TurnSimilarity]
) -> CheatSignal | None:
    hits = [s for s in similarities if s.ratio >= SIMILARITY_RATIO]
    if not hits:
        return None
    by_index = {t.index: t for t in turns}
    details = ";".join(
        f"第{s.index}题「{_excerpt(by_index[s.index].question)}」相似比 {s.ratio:.2f}"
        for s in sorted(hits, key=lambda s: -s.ratio)
        if s.index in by_index
    )
    return CheatSignal(
        kind="ai_similarity",
        severity="high" if len(hits) >= SIMILARITY_HIGH_COUNT else "medium",
        evidence=(
            f"{len(similarities)} 个长回答中有 {len(hits)} 个与 AI 对同一问题生成的答案高度相似"
            f"(相似比≥{SIMILARITY_RATIO};1.00 表示与 AI 答案彼此之间一样相像)。{details}。"
            "标准知识题的正确答案本身就容易与 AI 答案接近,请重点看开放题和经历题。"
        ),
    )
