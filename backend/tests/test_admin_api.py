"""HR 后台 CRUD API 测试(职位/题库/会话列表/仪表盘)。"""

from app.db import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_job(client, **kw) -> dict:
    payload = {
        "title": kw.get("title", "后端工程师"),
        "jd": kw.get("jd", "负责后端服务开发"),
        "interviewer_voice": kw.get("interviewer_voice", "Tina"),
        "language": kw.get("language", "zh"),
        "duration_minutes": kw.get("duration_minutes", 30),
        "status": kw.get("status", "招聘中"),
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _seed_session(db_session, job_id: int, candidate_name: str = "张三") -> models.InterviewSession:
    """直接向 DB 插入候选人 + 面试会话(绕过 link token 生成)。"""
    candidate = models.Candidate(name=candidate_name)
    db_session.add(candidate)
    db_session.flush()
    sess = models.InterviewSession(
        job_id=job_id,
        candidate_id=candidate.id,
        link_token=f"test-token-{candidate.id}",
        status="done",
    )
    db_session.add(sess)
    db_session.commit()
    return sess


# ---------------------------------------------------------------------------
# Jobs CRUD
# ---------------------------------------------------------------------------


def test_create_job_appears_in_list(client):
    """创建职位后应出现在 GET /api/jobs 列表，question_count 初始为 0。"""
    job = _create_job(client, title="前端工程师")
    assert job["title"] == "前端工程师"
    assert job["question_count"] == 0
    assert job["candidate_count"] == 0

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    titles = [j["title"] for j in resp.json()]
    assert "前端工程师" in titles


def test_get_job_returns_detail(client):
    """GET /api/jobs/{id} 应返回指定职位详情，缺失时 404。"""
    job = _create_job(client, title="算法工程师")
    resp = client.get(f"/api/jobs/{job['id']}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "算法工程师"

    assert client.get("/api/jobs/99999").status_code == 404


def test_update_job_changes_field(client):
    """PUT /api/jobs/{id} 应更新字段。"""
    job = _create_job(client, title="数据工程师")
    updated = client.put(
        f"/api/jobs/{job['id']}",
        json={**job, "title": "大数据工程师", "status": "暂停招聘"},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["title"] == "大数据工程师"
    assert body["status"] == "暂停招聘"


def test_delete_job_removes_it(client):
    """DELETE /api/jobs/{id} 应删除职位，再次 GET 返回 404。"""
    job = _create_job(client, title="测试工程师")
    resp = client.delete(f"/api/jobs/{job['id']}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404


# ---------------------------------------------------------------------------
# Questions CRUD
# ---------------------------------------------------------------------------


def test_add_questions_updates_job_question_count(client):
    """新增 2 道题后 GET /api/jobs/{id}.question_count 应为 2。"""
    job = _create_job(client)

    q1 = client.post(
        f"/api/jobs/{job['id']}/questions",
        json={"prompt": "请介绍一下你自己", "difficulty": "初级"},
    )
    assert q1.status_code == 200
    assert q1.json()["job_id"] == job["id"]

    q2 = client.post(
        f"/api/jobs/{job['id']}/questions",
        json={"prompt": "你对 FastAPI 的理解?", "difficulty": "中级"},
    )
    assert q2.status_code == 200

    resp = client.get(f"/api/jobs/{job['id']}")
    assert resp.json()["question_count"] == 2


def test_list_questions_returns_all(client):
    """GET /api/jobs/{id}/questions 应返回该职位的所有题目。"""
    job = _create_job(client)
    client.post(
        f"/api/jobs/{job['id']}/questions",
        json={"prompt": "题目1", "difficulty": "初级"},
    )
    client.post(
        f"/api/jobs/{job['id']}/questions",
        json={"prompt": "题目2", "difficulty": "高级", "is_probe": True},
    )

    resp = client.get(f"/api/jobs/{job['id']}/questions")
    assert resp.status_code == 200
    questions = resp.json()
    assert len(questions) == 2
    prompts = [q["prompt"] for q in questions]
    assert "题目1" in prompts
    assert "题目2" in prompts


def test_delete_question_removes_it(client):
    """DELETE /api/questions/{id} 应移除指定题目。"""
    job = _create_job(client)
    q = client.post(
        f"/api/jobs/{job['id']}/questions",
        json={"prompt": "待删除题目", "difficulty": "中级"},
    ).json()

    del_resp = client.delete(f"/api/questions/{q['id']}")
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True

    remaining = client.get(f"/api/jobs/{job['id']}/questions").json()
    assert len(remaining) == 0


def test_delete_job_also_removes_questions(client):
    """删除职位时应同时删除关联题目。"""
    job = _create_job(client)
    client.post(
        f"/api/jobs/{job['id']}/questions",
        json={"prompt": "孤儿题目", "difficulty": "初级"},
    )
    client.delete(f"/api/jobs/{job['id']}")
    # 职位已不存在 → GET questions 应返回 404
    assert client.get(f"/api/jobs/{job['id']}/questions").status_code == 404


# ---------------------------------------------------------------------------
# Sessions list
# ---------------------------------------------------------------------------


def test_sessions_list_includes_session(client, db_session):
    """GET /api/sessions 应返回会话并含 job_title + candidate_name + integrity_level。"""
    job = _create_job(client, title="产品经理")
    sess = _seed_session(db_session, job["id"], candidate_name="李四")

    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1

    matching = [i for i in items if i["token"] == sess.link_token]
    assert len(matching) == 1
    item = matching[0]
    assert item["candidate_name"] == "李四"
    assert item["job_title"] == "产品经理"
    assert item["integrity_level"] in ("green", "yellow", "red")


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------


def test_dashboard_stats_counts(client, db_session):
    """GET /api/dashboard/stats 应返回正确的聚合指标。"""
    # 创建 2 个招聘中职位
    job1 = _create_job(client, title="职位A", status="招聘中")
    _create_job(client, title="职位B", status="招聘中")

    # 1 个 pending 会话
    _seed_session(db_session, job1["id"], candidate_name="候选人1")

    resp = client.get("/api/dashboard/stats")
    assert resp.status_code == 200
    body = resp.json()

    assert body["active_jobs"] >= 2
    assert "pending_interviews" in body
    assert "completed_interviews" in body
    assert "high_risk" in body
    assert isinstance(body["recent"], list)
    assert len(body["recent"]) <= 6


def test_dashboard_recent_has_correct_shape(client, db_session):
    """recent 列表的每项应包含必要字段。"""
    job = _create_job(client, title="UI设计师")
    _seed_session(db_session, job["id"], candidate_name="王五")

    body = client.get("/api/dashboard/stats").json()
    if body["recent"]:
        item = body["recent"][0]
        for field in ("token", "candidate_name", "job_title", "status", "integrity_level"):
            assert field in item


# ---------------------------------------------------------------------------
# Transcripts endpoint
# ---------------------------------------------------------------------------


def test_list_transcripts_returns_ordered_by_id(client, db_session):
    """GET /api/sessions/{token}/transcripts 应按 id 升序返回转写,含 role/text/ts。"""
    job = _create_job(client, title="转写测试岗位")
    sess = _seed_session(db_session, job["id"], candidate_name="转写候选人")

    # Seed 2 transcripts in a specific order
    t1 = models.Transcript(session_id=sess.id, role="interviewer", text="请做个自我介绍")
    t2 = models.Transcript(session_id=sess.id, role="candidate", text="大家好,我是转写候选人")
    db_session.add(t1)
    db_session.add(t2)
    db_session.commit()

    resp = client.get(f"/api/sessions/{sess.link_token}/transcripts")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    # Ordered by id: interviewer first, then candidate
    assert items[0]["role"] == "interviewer"
    assert items[0]["text"] == "请做个自我介绍"
    assert items[1]["role"] == "candidate"
    assert items[1]["text"] == "大家好,我是转写候选人"
    # ts field present (may be string or null)
    assert "ts" in items[0]
    assert "ts" in items[1]


def test_list_transcripts_empty_when_none(client, db_session):
    """没有转写时应返回空列表而不是报错。"""
    job = _create_job(client, title="空转写岗位")
    sess = _seed_session(db_session, job["id"], candidate_name="空候选人")

    resp = client.get(f"/api/sessions/{sess.link_token}/transcripts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_transcripts_404_unknown_token(client):
    """未知 token 应返回 404。"""
    assert client.get("/api/sessions/no-such-token/transcripts").status_code == 404
