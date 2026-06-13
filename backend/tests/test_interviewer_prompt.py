from app.prompts.interviewer import build_interviewer_instructions, opener_for


_QUESTIONS = [
    {"prompt": "什么是数据库索引?", "difficulty": "中级"},
    {"prompt": "解释 TCP 三次握手。", "difficulty": "高级"},
]


def test_zh_instructions_include_jd_and_each_question():
    out = build_interviewer_instructions(
        job_title="后端工程师", jd="负责后端服务开发",
        questions=_QUESTIONS, language="zh", candidate_name="张三", duration_minutes=45,
    )
    assert "后端工程师" in out
    assert "负责后端服务开发" in out
    assert "什么是数据库索引?" in out
    assert "解释 TCP 三次握手。" in out
    assert "张三" in out
    assert "45" in out
    # 难度标注出现
    assert "中级" in out and "高级" in out


def test_en_language_switches_persona():
    out = build_interviewer_instructions(
        job_title="Backend Engineer", jd="Build backend services",
        questions=[{"prompt": "What is a DB index?", "difficulty": "medium"}],
        language="en",
    )
    assert "interviewer" in out.lower()
    assert "What is a DB index?" in out
    # 不应混入中文人设主体
    assert "面试官" not in out


def test_empty_questions_still_builds():
    out = build_interviewer_instructions(
        job_title="X", jd="Y", questions=[], language="zh",
    )
    assert "X" in out and "Y" in out


def test_opener_for_language():
    assert "中文" in opener_for("zh")
    assert "English" in opener_for("en")
