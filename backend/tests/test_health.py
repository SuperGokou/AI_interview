def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "database" in body
    assert set(body["models"].keys()) == {"realtime", "scoring"}
    assert isinstance(body["models"]["realtime"], bool)
    assert isinstance(body["models"]["scoring"], bool)
