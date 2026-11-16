from app.db import models


def make_session(client):
    job = client.post('/api/jobs', json={'title':'测试职位','jd':'测试职责'}).json()
    return client.post('/api/sessions', json={'job_id':job['id'],'candidate_name':'测试候选人'}).json()['token']


def test_supervisor_links_and_isolated_transcripts(client, db_session):
    token = make_session(client)
    response = client.post(f'/api/sessions/{token}/supervisors', json={'count':2})
    assert response.status_code == 200
    links = response.json()['links']
    assert len(links) == 2
    assert len({link['token'] for link in links} | {token}) == 3
    assert client.get(f'/api/sessions/{token}/supervisors').json() == links
    st = links[0]['token']
    info = client.get(f'/api/supervisors/{st}').json()
    assert info['candidate_name'] == '测试候选人'
    assert sum(p['is_current'] for p in info['supervisors']) == 1
    assert all('token' not in p for p in info['supervisors'])
    assert client.get(f'/api/supervisors/{token}').status_code == 404
    assert client.get(f'/api/sessions/{st}').status_code == 404
    sess = db_session.query(models.InterviewSession).filter_by(link_token=token).one()
    other_token = make_session(client)
    other = db_session.query(models.InterviewSession).filter_by(link_token=other_token).one()
    sess.status = 'active'
    db_session.add_all([models.Transcript(session_id=sess.id,role='candidate',text='本场回答'),models.Transcript(session_id=other.id,role='candidate',text='另一场私密回答')])
    db_session.commit()
    feed = client.get(f'/api/supervisors/{st}/transcripts').json()
    assert feed['live'] is True
    assert [t['text'] for t in feed['transcripts']] == ['本场回答']
    assert client.get('/api/supervisors/invalid/transcripts').status_code == 404


def test_supervisor_labels_limits_and_missing_session(client):
    token = make_session(client)
    r = client.post(f'/api/sessions/{token}/supervisors',json={'labels':['技术主管','HR']})
    assert r.status_code == 200
    assert [x['label'] for x in r.json()['links']] == ['技术主管','HR']
    assert client.post(f'/api/sessions/{token}/supervisors',json={'count':0}).status_code == 422
    assert client.post('/api/sessions/missing/supervisors',json={'count':2}).status_code == 404
