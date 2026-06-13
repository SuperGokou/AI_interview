from app.core.scoring import ReportGenerator


class _Fake:
    def __init__(self, resp):
        self._r = resp
        self.last = None

    def complete(self, *, system, user, temperature):
        self.last = {"system": system, "user": user, "temperature": temperature}
        return self._r


_GOOD = (
    '{"score_professional":82,"score_communication":75,"score_job_match":80,'
    '"score_demeanor":70,"ai_risk_level":"low","feedback":"专业扎实","overall":"建议进入复面"}'
)


def test_generate_parses_scores():
    g = ReportGenerator(client=_Fake(_GOOD))
    out = g.generate(
        job_title="后端工程师", jd="负责后端",
        transcripts=[
            {"role": "interviewer", "text": "什么是数据库索引?"},
            {"role": "candidate", "text": "加速查询的数据结构"},
        ],
        questions=[{"prompt": "什么是数据库索引?", "key_points": "B+树", "reference_answer": "...", "difficulty": "中级"}],
        cheat_summary="诚信:green",
    )
    assert out["score_professional"] == 82
    assert out["score_communication"] == 75
    assert out["ai_risk_level"] == "low"
    assert out["overall"] == "建议进入复面"


def test_generate_prompt_includes_all_inputs():
    f = _Fake(_GOOD)
    ReportGenerator(client=f).generate(
        job_title="算法工程师", jd="JD内容XYZ",
        transcripts=[{"role": "candidate", "text": "我的回答ABC"}],
        questions=[{"prompt": "题目Q1", "key_points": "K1", "reference_answer": "R1", "difficulty": "高级"}],
        cheat_summary="诚信:red,1次multi_person",
    )
    u = f.last["user"]
    assert "JD内容XYZ" in u
    assert "题目Q1" in u
    assert "我的回答ABC" in u
    assert "red" in u


def test_generate_handles_code_fence_and_null_demeanor():
    g = ReportGenerator(client=_Fake(
        '```json\n{"score_professional":50,"score_communication":50,"score_job_match":50,'
        '"score_demeanor":null,"ai_risk_level":"medium","feedback":"f","overall":"o"}\n```'
    ))
    out = g.generate(job_title="x", jd="y", transcripts=[], questions=[], cheat_summary="")
    assert out["score_demeanor"] is None
    assert out["score_professional"] == 50


def test_generate_unparseable_is_safe():
    out = ReportGenerator(client=_Fake("这不是 JSON")).generate(
        job_title="x", jd="y", transcripts=[], questions=[], cheat_summary=""
    )
    assert out["overall"] == "评分解析失败"
    assert out["score_professional"] is None
