def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "database" in body
    assert set(body["models"].keys()) == {"qwen", "deepseek"}
    assert isinstance(body["models"]["qwen"], bool)
    assert isinstance(body["models"]["deepseek"], bool)
