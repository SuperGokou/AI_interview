"""Post-interview integrity signals: timing, pure signal rules, review parsing."""

import json

import pytest

from app.core.answer_review import reference_answers, score_turns
from app.core.answer_timing import TurnTimer
from app.core.integrity_signals import (
    Turn,
    TurnScore,
    TurnSimilarity,
    build_turns,
    cosine,
    latency_signal,
    probe_gap_signal,
    similarity_ratio,
    similarity_signal,
)

LONG = "这是一个足够长的回答。" * 10


def _turn(index, latency_ms=None, answer=LONG, question="请介绍一下项目"):
    return Turn(index=index, question=question, answer=answer, latency_ms=latency_ms)


# --- TurnTimer --------------------------------------------------------------


def test_latency_is_measured_from_estimated_playback_end():
    timer = TurnTimer(sample_rate=24000)
    timer.on_interviewer_audio(48000, now=10.0)  # 1 s of PCM16 at 24 kHz
    timer.on_interviewer_audio(48000, now=10.1)  # another second, arrives early
    timer.on_candidate_speech_started(now=15.0)  # playback ended at 12.0
    assert timer.on_candidate_transcript().latency_ms == 3000


def test_barge_in_counts_as_zero_and_pauses_do_not_restart_the_clock():
    timer = TurnTimer(sample_rate=24000)
    timer.on_interviewer_audio(480000, now=0.0)  # 10 s question
    timer.on_candidate_speech_started(now=4.0)  # interrupts
    timer.on_candidate_speech_started(now=9.0)  # pause inside the same answer
    assert timer.on_candidate_transcript().latency_ms == 0
    assert timer.on_candidate_transcript().latency_ms is None  # second utterance of the answer


def test_latency_survives_the_next_reply_starting_before_the_transcript():
    timer = TurnTimer(sample_rate=24000)
    timer.on_interviewer_audio(48000, now=0.0)
    timer.on_candidate_speech_started(now=3.0)
    timer.on_interviewer_audio(48000, now=8.0)  # next question begins streaming
    assert timer.on_candidate_transcript().latency_ms == 2000


def test_no_latency_without_a_question_or_speech_onset():
    timer = TurnTimer(sample_rate=24000)
    timer.on_candidate_speech_started(now=1.0)
    assert timer.on_candidate_transcript().latency_ms is None


# --- build_turns ------------------------------------------------------------


def test_build_turns_merges_split_utterances_and_keeps_first_latency():
    turns = build_turns(
        [
            ("interviewer", "你好,", None),
            ("interviewer", "请自我介绍。", None),
            ("candidate", "我叫张三,", 1200),
            ("candidate", "做后端。", None),
            ("interviewer", "讲讲索引。", None),
            ("candidate", "B+树。", 800),
        ]
    )
    assert [(t.index, t.question, t.answer, t.latency_ms) for t in turns] == [
        (1, "你好,请自我介绍。", "我叫张三,做后端。", 1200),
        (2, "讲讲索引。", "B+树。", 800),
    ]


def test_build_turns_ignores_trailing_question_and_handles_leading_answer():
    turns = build_turns([("candidate", "喂?", None), ("interviewer", "开始吧", None)])
    assert len(turns) == 1 and turns[0].question == ""


# --- latency_pattern --------------------------------------------------------


def test_consistent_long_pauses_raise_a_latency_signal():
    signal = latency_signal([_turn(1, 5000), _turn(2, 5400), _turn(3, 4800)])
    assert signal.kind == "latency_pattern" and signal.severity == "medium"
    assert "第2题 5.4s" in signal.evidence


@pytest.mark.parametrize(
    "latencies",
    [
        [500, 900, 700],  # quick, natural
        [5000, 12000, 1000],  # long on average but irregular: thinking, not reading
        [5000, 5200],  # too few answers
    ],
)
def test_natural_timing_raises_nothing(latencies):
    turns = [_turn(i + 1, ms) for i, ms in enumerate(latencies)]
    assert latency_signal(turns) is None


def test_short_answers_are_excluded_from_the_latency_pattern():
    turns = [_turn(i, 5000, answer="好的") for i in range(1, 5)]
    assert latency_signal(turns) is None


# --- probe_gap --------------------------------------------------------------


def test_strong_main_answers_with_weak_probes_raise_a_signal():
    turns = [_turn(i) for i in range(1, 5)]
    scores = [
        TurnScore(1, "main", 90), TurnScore(2, "probe", 30),
        TurnScore(3, "main", 85), TurnScore(4, "probe", 40),
    ]
    signal = probe_gap_signal(turns, scores)
    assert signal.kind == "probe_gap" and signal.severity == "high"
    assert "落差 52 分" in signal.evidence


def test_single_weak_probe_is_only_medium():
    scores = [TurnScore(1, "main", 90), TurnScore(2, "probe", 20)]
    assert probe_gap_signal([_turn(1), _turn(2)], scores).severity == "medium"


@pytest.mark.parametrize(
    "scores",
    [
        [TurnScore(1, "main", 60), TurnScore(2, "probe", 20)],  # weak everywhere
        [TurnScore(1, "main", 90), TurnScore(2, "probe", 75)],  # holds up under probing
        [TurnScore(1, "main", 90), TurnScore(2, "other", 10)],  # no probes asked
    ],
)
def test_no_probe_gap_signal(scores):
    assert probe_gap_signal([_turn(1), _turn(2)], scores) is None


# --- ai_similarity ----------------------------------------------------------


def test_cosine_and_ratio():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([0, 0], [1, 0]) == 0.0
    refs = [[1.0, 0.0], [0.8, 0.6]]  # cosine between them: 0.8
    assert similarity_ratio([1.0, 0.0], refs) == pytest.approx(0.9 / 0.8)
    assert similarity_ratio([0.0, 1.0], refs) == pytest.approx(0.3 / 0.8)
    assert similarity_ratio([1.0, 0.0], [[1.0, 0.0]]) is None  # cannot calibrate


def test_similarity_signal_escalates_with_the_number_of_hits():
    turns = [_turn(i) for i in range(1, 5)]
    one = similarity_signal(turns, [TurnSimilarity(1, 0.99), TurnSimilarity(2, 0.70)])
    assert one.severity == "medium" and "2 个长回答中有 1 个" in one.evidence
    many = similarity_signal(turns, [TurnSimilarity(i, 1.01) for i in range(1, 4)])
    assert many.severity == "high"
    assert similarity_signal(turns, [TurnSimilarity(1, 0.80)]) is None


# --- answer_review ----------------------------------------------------------


class _Client:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def complete(self, *, system, user, temperature=0.3):
        self.calls.append(user)
        return self.reply


def test_score_turns_keeps_only_well_formed_entries():
    reply = json.dumps(
        {
            "turns": [
                {"index": 1, "kind": "main", "score": 88},
                {"index": 2, "kind": "probe", "score": 140},  # out of range
                {"index": 9, "kind": "main", "score": 50},  # unknown turn
                {"index": 2, "kind": "followup", "score": 50},  # unknown kind
                "garbage",
            ]
        }
    )
    client = _Client(f"```json\n{reply}\n```")
    scores = score_turns(client, [_turn(1), _turn(2)], [{"prompt": "探针题", "is_probe": True}])
    assert scores == [TurnScore(1, "main", 88)]
    assert "[探针] 探针题" in client.calls[0]


def test_score_turns_makes_no_call_without_turns():
    client = _Client("{}")
    assert score_turns(client, [], []) == []
    assert client.calls == []


def test_reference_answers_parses_and_rejects_bad_output():
    assert reference_answers(_Client('{"answers": [" a ", "", 3, "b"]}'), "q") == ["a", "b"]
    with pytest.raises(ValueError):
        reference_answers(_Client("sorry"), "q")
    with pytest.raises(ValueError):
        reference_answers(_Client('{"answers": "one"}'), "q")
