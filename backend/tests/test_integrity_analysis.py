"""Post-interview analysis end to end: persistence, fault isolation, websocket wiring."""

import asyncio
import json

from app.core.embeddings import OpenAICompatibleEmbedder
from app.core.integrity_analysis import analyze_integrity
from app.db import models

LONG = "我在上一家公司负责订单系统的重构,把单体拆成了服务。" * 4
AI_STYLE = "首先,索引是一种数据结构;其次,它能加速查询;最后,需要权衡写入成本。" * 3


def _seed(db, rows, *, token="tok-analysis"):
    """rows: (role, text, latency_ms)."""
    job = models.Job(title="后端", jd="x", interviewer_voice="Tina")
    cand = models.Candidate(name="张三")
    db.add_all([job, cand])
    db.commit()
    db.add(models.Question(job_id=job.id, prompt="讲讲数据库索引", is_probe=False))
    sess = models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token=token)
    db.add(sess)
    db.commit()
    for role, text, latency in rows:
        row = models.Transcript(session_id=sess.id, role=role, text=text)
        db.add(row)
        db.flush()
        if latency is not None:
            db.add(models.AnswerMetric(session_id=sess.id, transcript_id=row.id, latency_ms=latency))
    db.commit()
    return sess.id


INTERVIEW = [
    ("interviewer", "讲讲数据库索引", None),
    ("candidate", AI_STYLE, 5000),
    ("interviewer", "你们线上那张表有多少行?", None),
    ("candidate", LONG, 5300),
    ("interviewer", "为什么不用哈希索引?", None),
    ("candidate", LONG, 4900),
]


class _ReviewClient:
    """Scores turn 1 as a strong main answer and the follow-ups as weak probes."""

    def __init__(self, *, fail_scoring=False):
        self.fail_scoring = fail_scoring

    def complete(self, *, system, user, temperature=0.3):
        if "turns" in system:
            if self.fail_scoring:
                raise RuntimeError("scoring provider down")
            return json.dumps(
                {
                    "turns": [
                        {"index": 1, "kind": "main", "score": 92},
                        {"index": 2, "kind": "probe", "score": 35},
                        {"index": 3, "kind": "probe", "score": 30},
                    ]
                }
            )
        return json.dumps({"answers": ["ref-a", "ref-b", "ref-c"]})


class _Embedder:
    """AI-style text and the references share a direction; everything else is orthogonal."""

    def embed(self, texts):
        return [[1.0, 0.0] if (t.startswith("ref-") or t == AI_STYLE) else [0.0, 1.0] for t in texts]


def _events(db, session_id):
    db.expire_all()
    rows = db.query(models.CheatEvent).filter_by(session_id=session_id).all()
    return {e.kind: e for e in rows}


def test_all_three_signals_are_recorded_with_evidence(db_session):
    sid = _seed(db_session, INTERVIEW)
    analyze_integrity(db_session, sid, client=_ReviewClient(), embedder=_Embedder())
    events = _events(db_session, sid)
    assert set(events) == {"latency_pattern", "probe_gap", "ai_similarity"}
    assert events["probe_gap"].severity == "high"
    assert "第1题" in events["ai_similarity"].evidence
    assert "中位 5.0s" in events["latency_pattern"].evidence


def test_rerunning_replaces_rather_than_duplicates(db_session):
    sid = _seed(db_session, INTERVIEW)
    db_session.add(models.CheatEvent(session_id=sid, kind="ai_text", severity="high"))
    db_session.commit()
    for _ in range(2):
        analyze_integrity(db_session, sid, client=_ReviewClient(), embedder=_Embedder())
    db_session.expire_all()
    kinds = [e.kind for e in db_session.query(models.CheatEvent).filter_by(session_id=sid)]
    assert sorted(kinds) == ["ai_similarity", "ai_text", "latency_pattern", "probe_gap"]


def test_without_model_services_only_the_timing_signal_runs(db_session):
    sid = _seed(db_session, INTERVIEW)
    analyze_integrity(db_session, sid, client=None, embedder=None)
    assert set(_events(db_session, sid)) == {"latency_pattern"}


def test_scoring_failure_does_not_block_the_other_signals(db_session):
    sid = _seed(db_session, INTERVIEW)
    analyze_integrity(
        db_session, sid, client=_ReviewClient(fail_scoring=True), embedder=_Embedder()
    )
    assert set(_events(db_session, sid)) == {"latency_pattern", "ai_similarity"}


def test_embedding_failure_does_not_block_the_other_signals(db_session):
    class _Broken:
        def embed(self, texts):
            raise RuntimeError("embedding service down")

    sid = _seed(db_session, INTERVIEW)
    analyze_integrity(db_session, sid, client=_ReviewClient(), embedder=_Broken())
    assert set(_events(db_session, sid)) == {"latency_pattern", "probe_gap"}


def test_natural_interview_records_nothing(db_session):
    sid = _seed(
        db_session,
        [
            ("interviewer", "讲讲数据库索引", None),
            ("candidate", LONG, 600),
            ("interviewer", "表有多少行?", None),
            ("candidate", LONG, 2400),
        ],
    )

    class _Fair(_ReviewClient):
        def complete(self, *, system, user, temperature=0.3):
            if "turns" in system:
                return json.dumps(
                    {"turns": [{"index": 1, "kind": "main", "score": 80},
                               {"index": 2, "kind": "probe", "score": 78}]}
                )
            return super().complete(system=system, user=user, temperature=temperature)

    analyze_integrity(db_session, sid, client=_Fair(), embedder=_Embedder())
    assert _events(db_session, sid) == {}


def test_embedder_returns_vectors_in_input_order():
    class _Item:
        def __init__(self, index, embedding):
            self.index, self.embedding = index, embedding

    class _Embeddings:
        def create(self, *, model, input):
            assert model == "m" and input == ["a", "b"]
            return type("R", (), {"data": [_Item(1, [0.0, 1.0]), _Item(0, [1.0, 0.0])]})()

    client = type("C", (), {"embeddings": _Embeddings()})()
    embedder = OpenAICompatibleEmbedder(client=client, model="m")
    assert embedder.embed(["a", "b"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert embedder.embed([]) == []


# --- websocket wiring -------------------------------------------------------


class _Bridge:
    """Replays a question (1 s of audio), a speech onset and the answer."""

    def __init__(self, **_kwargs):
        self._pending = [
            {"kind": "audio", "data": b"\x00" * 48000},
            {"kind": "transcript", "text": "讲讲数据库索引"},
            {"kind": "speech_started"},
            {"kind": "user_transcript", "text": LONG},
        ]

    async def connect(self):
        pass

    async def events(self):
        if self._pending:
            return self._pending.pop(0)
        await asyncio.Event().wait()

    async def trigger_response(self, instructions=""):
        pass

    async def send_audio(self, pcm):
        pass

    async def send_image(self, jpeg):
        pass

    async def close(self):
        pass


class _Reports:
    summaries: list[str] = []

    def generate(self, **kwargs):
        type(self).summaries.append(kwargs["cheat_summary"])
        return {
            "score_professional": 1, "score_communication": 1, "score_job_match": 1,
            "score_demeanor": None, "ai_risk_level": "low", "feedback": "f", "overall": "o",
        }


def test_websocket_records_latency_and_runs_analysis_before_the_report(
    client, db_session, monkeypatch
):
    sid = _seed(db_session, [], token="tok-ws-analysis")
    _Reports.summaries = []
    monkeypatch.setattr("app.api.interview_ws.bridge_factory", _Bridge)
    monkeypatch.setattr("app.api.interview_ws.ai_detector_factory", lambda: object())
    monkeypatch.setattr("app.api.interview_ws.report_generator_factory", _Reports)
    monkeypatch.setattr(
        "app.api.interview_ws.review_client_factory",
        lambda: type("C", (), {"complete": lambda self, **_k: json.dumps(
            {"turns": [{"index": 1, "kind": "main", "score": 90}],
             "answers": ["ref-a", "ref-b"]})})(),
    )

    class _Same:
        def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr("app.api.interview_ws.embedder_factory", lambda: _Same())

    with client.websocket_connect("/ws/interview?token=tok-ws-analysis") as ws:
        frames = [ws.receive_json() for _ in range(3)]
    assert [f["type"] for f in frames] == ["audio", "transcript", "user_transcript"]

    db_session.expire_all()
    metric = db_session.query(models.AnswerMetric).filter_by(session_id=sid).one()
    assert metric.latency_ms == 0  # onset arrived before the 1 s clip finished playing
    assert "ai_similarity" in _events(db_session, sid)
    assert "ai_similarity" in _Reports.summaries[0]
