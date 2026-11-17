from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)

def test_health():
    r = client.get('/health')
    assert r.status_code == 200 and r.json()['external_writes'] is False

def test_draft():
    r = client.post('/draft', json={"project_id":"demo", "run_id":"r1", "objective":"Describe an API"})
    assert r.status_code == 200
    assert r.json()['status'] == 'awaiting_human_review'
