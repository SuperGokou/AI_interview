from pathlib import Path


def test_admin_requires_credentials(client):
    client.auth = None
    for path in ['/api/jobs', '/api/sessions', '/admin/jobs', '/docs', '/api/sessions/x/report', '/api/sessions/x/supervisors']:
        assert client.get(path).status_code == 401
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/sessions/unknown').status_code == 404
    assert client.get('/api/supervisors/unknown').status_code == 404


def test_missing_admin_config_fails_closed(client, monkeypatch):
    monkeypatch.delenv('ADMIN_PASSWORD')
    assert client.get('/api/jobs').status_code == 503


def test_demo_disabled_by_default(client, monkeypatch):
    monkeypatch.delenv('DEV_ENDPOINTS')
    assert client.post('/api/dev/demo-session').status_code == 404


def test_cross_origin_admin_write_denied(client):
    assert client.post('/api/jobs', headers={'Origin': 'https://untrusted.example'}, json={}).status_code == 403


def test_spa_cannot_escape_static_root(client, monkeypatch, tmp_path):
    import app.main as main
    public = tmp_path / 'public'
    public.mkdir()
    (public / 'index.html').write_text('application')
    (tmp_path / 'secret.txt').write_text('private')
    try:
        (public / 'leak.txt').symlink_to(tmp_path / 'secret.txt')
        symlinked = True
    except OSError:  # Windows without the symlink privilege: the other checks still apply
        symlinked = False
    monkeypatch.setattr(main, 'FRONTEND_DIR', public)
    assert client.get('/%2e%2e/secret.txt').status_code == 404
    if symlinked:
        assert client.get('/leak.txt').status_code == 404
    assert client.get('/api/not-a-route').status_code == 404
    assert client.get('/interview').status_code == 200
