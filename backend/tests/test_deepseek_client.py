from app.core.deepseek_client import DeepSeekClient


class _FakeCompletions:
    def __init__(self, recorder):
        self._recorder = recorder

    def create(self, *, model, messages, temperature):
        self._recorder["model"] = model
        self._recorder["messages"] = messages
        self._recorder["temperature"] = temperature

        class _Msg:
            content = "判分结果:8/10"

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()


class _FakeClient:
    def __init__(self, recorder):
        self.chat = type("C", (), {"completions": _FakeCompletions(recorder)})()


def test_complete_returns_model_text_and_sends_system_user():
    recorder: dict = {}
    client = DeepSeekClient(model="deepseek-chat", client=_FakeClient(recorder))
    out = client.complete(system="你是评分官", user="评估这段回答", temperature=0.2)
    assert out == "判分结果:8/10"
    assert recorder["model"] == "deepseek-chat"
    assert recorder["messages"][0] == {"role": "system", "content": "你是评分官"}
    assert recorder["messages"][1] == {"role": "user", "content": "评估这段回答"}
    assert recorder["temperature"] == 0.2
