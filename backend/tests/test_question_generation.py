"""Interviewer playbook, per-question context, AI question drafting, column upgrade."""

import json

import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.question_generator import generate_questions
from app.db import models
from app.prompts.interviewer import build_interviewer_instructions, opener_for

JOB = {"title": "后端工程师", "jd": "负责订单系统,技术栈 Go + MySQL + Kafka",
       "interviewer_voice": "Tina", "language": "zh"}

REPLY = {
    "questions": [
        {
            "prompt": "讲讲你们订单表是怎么分库分表的?",
            "key_points": "分片键选择;扩容方案",
            "reference_answer": "按用户 ID 哈希分片。",
            "difficulty": "高级",
            "follow_ups": ["单表多少行?", "扩容时怎么迁移数据?", "热点用户怎么处理?", "第四个应被截断"],
        },
        {"prompt": "Kafka 怎么保证不丢消息?", "difficulty": "困难", "follow_ups": "不是列表"},
        {"prompt": "   ", "difficulty": "初级"},
        "garbage",
    ]
}


class _Client:
    def __init__(self, reply=REPLY):
        self.reply, self.prompts = reply, []

    def complete(self, *, system, user, temperature=0.3):
        self.prompts.append(user)
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


# --- interviewer instructions ----------------------------------------------


def test_instructions_carry_key_points_and_follow_ups_but_never_reference_answers():
    out = build_interviewer_instructions(
        job_title="后端", jd="x", language="zh",
        questions=[{
            "prompt": "什么是索引?", "difficulty": "中级",
            "key_points": "B+树;最左前缀", "follow_ups": "你们最大的表多少行?\n\n为什么不用哈希?",
            "reference_answer": "绝密标准答案",
        }],
    )
    assert "考点(保密,勿透露): B+树;最左前缀" in out
    assert "参考追问: 你们最大的表多少行? / 为什么不用哈希?" in out
    assert "绝密标准答案" not in out
    assert "【考点保密】" in out and "【保持角色】" in out


def test_question_context_is_bounded():
    out = build_interviewer_instructions(
        job_title="后端", jd="x",
        questions=[{"prompt": "q", "key_points": "k" * 1000,
                    "follow_ups": "\n".join(f"追问{i}" for i in range(10))}],
    )
    assert "k" * 201 not in out
    assert "追问2" in out and "追问3" not in out


def test_english_playbook_has_no_chinese():
    out = build_interviewer_instructions(
        job_title="Backend", jd="x", language="en",
        questions=[{"prompt": "What is an index?", "key_points": "B-tree", "follow_ups": "How big?"}],
    )
    assert "Key points (confidential): B-tree" in out
    assert "Suggested follow-ups: How big?" in out
    assert "考点" not in out and "面试官" not in out


def test_interviewer_identifies_as_the_configured_product():
    out = build_interviewer_instructions(job_title="后端", jd="x", questions=[])
    assert "你是 KY-BOT,江苏坤曜智能科技有限公司旗下专注于面试的 AI 模型" in out
    assert "不要提及其他公司或其他模型的名称" in out
    assert "KY-BOT" in opener_for("zh") and "江苏坤曜智能科技有限公司" in opener_for("zh")

    custom = build_interviewer_instructions(
        job_title="Backend", jd="x", questions=[], language="en",
        interviewer_name="ACME-HR", interviewer_company="Acme Ltd",
    )
    assert "you are ACME-HR, an AI model from Acme Ltd" in custom
    assert "KY-BOT" not in custom
    assert "ACME-HR" in opener_for("en", name="ACME-HR", company="Acme Ltd")


def test_websocket_uses_the_configured_identity(client, db_session, monkeypatch):
    import asyncio
    from dataclasses import replace

    import app.api.interview_ws as ws_module

    captured = {}

    class _Bridge:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def connect(self): pass
        async def events(self): await asyncio.Event().wait()
        async def trigger_response(self, instructions=""): pass
        async def send_audio(self, pcm): pass
        async def send_image(self, jpeg): pass
        async def close(self): pass

    branded = replace(
        ws_module.get_settings(), interviewer_name="ACME-HR", interviewer_company="某某科技"
    )
    monkeypatch.setattr(ws_module, "get_settings", lambda: branded)
    job = models.Job(title="后端", jd="x", interviewer_voice="Tina")
    cand = models.Candidate(name="张三")
    db_session.add_all([job, cand])
    db_session.commit()
    db_session.add(models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token="tok-id"))
    db_session.commit()
    monkeypatch.setattr("app.api.interview_ws.bridge_factory", _Bridge)
    monkeypatch.setattr("app.api.interview_ws.ai_detector_factory", lambda: object())
    with client.websocket_connect("/ws/interview?token=tok-id"):
        pass
    assert "你是 ACME-HR,某某科技旗下专注于面试的 AI 模型" in captured["instructions"]


# --- generator --------------------------------------------------------------


def test_generator_cleans_model_output():
    client = _Client()
    drafts = generate_questions(
        client, job_title="后端", jd="Go", language="zh", count=5,
        existing=["已有的题"], focus="数据库",
    )
    assert [d.prompt for d in drafts] == ["讲讲你们订单表是怎么分库分表的?", "Kafka 怎么保证不丢消息?"]
    assert len(drafts[0].follow_ups) == 3
    assert drafts[1].difficulty == "中级" and drafts[1].follow_ups == ()
    assert "- 已有的题" in client.prompts[0] and "数据库" in client.prompts[0]


def test_generator_skips_duplicates_and_respects_count():
    drafts = generate_questions(
        _Client(), job_title="后端", jd="Go", language="zh", count=1,
        existing=["讲讲你们订单表是怎么分库分表的?"],
    )
    assert [d.prompt for d in drafts] == ["Kafka 怎么保证不丢消息?"]


@pytest.mark.parametrize("reply", ["抱歉,我无法完成", {"questions": []}, {"questions": "x"}])
def test_generator_raises_when_nothing_usable(reply):
    with pytest.raises(ValueError):
        generate_questions(_Client(reply), job_title="后端", jd="Go", language="zh", count=3)


# --- API --------------------------------------------------------------------


def test_generate_endpoint_saves_drafts_to_the_bank(client, monkeypatch):
    fake = _Client()
    monkeypatch.setattr("app.api.questions.generator_client_factory", lambda: fake)
    job = client.post("/api/jobs", json=JOB).json()
    resp = client.post(f"/api/jobs/{job['id']}/questions/generate", json={"count": 3})
    assert resp.status_code == 200, resp.text
    created = resp.json()
    assert created[0]["follow_ups"] == "单表多少行?\n扩容时怎么迁移数据?\n热点用户怎么处理?"
    assert created[1]["follow_ups"] is None
    assert "Kafka" in fake.prompts[0]  # the job description reached the model
    assert len(client.get(f"/api/jobs/{job['id']}/questions").json()) == 2


def test_generate_endpoint_errors(client, monkeypatch):
    job = client.post("/api/jobs", json=JOB).json()
    url = f"/api/jobs/{job['id']}/questions/generate"
    monkeypatch.setattr("app.api.questions.generator_client_factory", lambda: None)
    assert client.post(url, json={}).status_code == 503
    monkeypatch.setattr("app.api.questions.generator_client_factory", lambda: _Client("oops"))
    assert client.post(url, json={}).status_code == 502
    assert client.post(url, json={"count": 99}).status_code == 422
    assert client.post("/api/jobs/9999/questions/generate", json={}).status_code == 404
    assert client.get(f"/api/jobs/{job['id']}/questions").json() == []


def test_follow_ups_round_trip_through_crud(client):
    job = client.post("/api/jobs", json=JOB).json()
    q = client.post(
        f"/api/jobs/{job['id']}/questions", json={"prompt": "讲讲索引", "follow_ups": "多少行?"}
    ).json()
    assert q["follow_ups"] == "多少行?"
    updated = client.put(f"/api/questions/{q['id']}", json={"prompt": "讲讲索引"}).json()
    assert updated["follow_ups"] is None


def test_websocket_gives_the_interviewer_key_points_and_follow_ups(client, db_session, monkeypatch):
    import asyncio

    captured = {}

    class _Bridge:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def connect(self): pass
        async def events(self): await asyncio.Event().wait()
        async def trigger_response(self, instructions=""): pass
        async def send_audio(self, pcm): pass
        async def send_image(self, jpeg): pass
        async def close(self): pass

    job = models.Job(title="后端", jd="x", interviewer_voice="Tina")
    cand = models.Candidate(name="张三")
    db_session.add_all([job, cand])
    db_session.commit()
    db_session.add(models.Question(
        job_id=job.id, prompt="讲讲索引", key_points="最左前缀",
        reference_answer="绝密标准答案", follow_ups="你们的表多少行?",
    ))
    db_session.add(models.InterviewSession(job_id=job.id, candidate_id=cand.id, link_token="tok-ctx"))
    db_session.commit()
    monkeypatch.setattr("app.api.interview_ws.bridge_factory", _Bridge)
    monkeypatch.setattr("app.api.interview_ws.ai_detector_factory", lambda: object())
    with client.websocket_connect("/ws/interview?token=tok-ctx"):
        pass
    assert "最左前缀" in captured["instructions"]
    assert "你们的表多少行?" in captured["instructions"]
    assert "绝密标准答案" not in captured["instructions"]


# --- schema upgrade ---------------------------------------------------------


def test_existing_database_gains_the_new_nullable_column(tmp_path, monkeypatch):
    import app.db.base as base

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:  # a questions table from before follow_ups existed
        conn.execute(text(
            "CREATE TABLE questions (id INTEGER PRIMARY KEY, job_id INTEGER, prompt TEXT,"
            " key_points TEXT, reference_answer TEXT, difficulty VARCHAR(16), is_probe BOOLEAN)"
        ))
        conn.execute(text("INSERT INTO questions (job_id, prompt) VALUES (1, '老题目')"))
    monkeypatch.setattr(base, "engine", engine)
    base.init_db()
    base.init_db()  # idempotent
    columns = {c["name"] for c in inspect(engine).get_columns("questions")}
    assert "follow_ups" in columns
    with engine.connect() as conn:
        assert conn.execute(text("SELECT prompt, follow_ups FROM questions")).one() == ("老题目", None)
    engine.dispose()
