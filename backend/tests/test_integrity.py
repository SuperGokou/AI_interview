from app.core.integrity import (
    CheatSignal,
    interpret_visual_observation,
    compute_integrity_level,
)


def test_interpret_known_flags_to_signals_with_severity():
    obs = {"flags": ["gaze_off_screen", "multi_person"], "detail": "视线偏离 8 秒"}
    signals = interpret_visual_observation(obs)
    kinds = {s.kind: s.severity for s in signals}
    assert kinds["gaze_off_screen"] == "medium"
    assert kinds["multi_person"] == "high"
    assert all(s.evidence == "视线偏离 8 秒" for s in signals)


def test_interpret_ignores_unknown_flags_and_empty():
    assert interpret_visual_observation({"flags": ["???"], "detail": "x"}) == []
    assert interpret_visual_observation({}) == []


def test_integrity_level_thresholds():
    assert compute_integrity_level([]) == "green"
    assert compute_integrity_level([CheatSignal("a", "medium")]) == "yellow"   # 3
    assert compute_integrity_level([CheatSignal("a", "high")]) == "red"        # 6
    assert compute_integrity_level(
        [CheatSignal("a", "medium"), CheatSignal("b", "medium")]
    ) == "red"  # 6


def test_integrity_level_accepts_dicts():
    assert compute_integrity_level([{"severity": "low"}]) == "green"   # 1
    assert compute_integrity_level(
        [{"severity": "medium"}, {"severity": "low"}]
    ) == "yellow"  # 4
