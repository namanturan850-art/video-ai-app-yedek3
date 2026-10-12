"""Stage 0: Gemini (free tier) is the default AI engine everywhere; Claude only
when the owner ticks it in Settings; Ollama stays the backup. No network."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from test_scripts import HEADERS

SETTINGS = {'X-AI-Video-Studio': 'settings'}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        yield client


def gemini(client):
    s = client.app.state.settings
    s.save('gemini', {'api_key': 'synthetic-gemini-key-7777'})
    s.record_gemini_models(s.gemini_config(), ['gemini-test-model'])
    s.save('gemini', {'model': 'gemini-test-model'})


def test_new_project_engine_is_gemini(client):
    project = client.post('/api/projects', json={'name': 'Yeni', 'topic': 'Rom'}).json()
    assert project['script_engine'] == 'gemini'


def test_script_screen_defaults_to_gemini_even_for_old_ollama_projects(client):
    old = client.post('/api/projects', json={'name': 'Eski', 'topic': 'Rom', 'script_engine': 'ollama'}).json()
    assert client.get(f'/api/projects/{old["id"]}/script').json()['default_provider'] == 'gemini'  # never Ollama by itself; the plan screen asks
    gemini(client)
    view = client.get(f'/api/projects/{old["id"]}/script').json()
    assert view['default_provider'] == 'gemini' and view['director']['engine'] == 'gemini' and not view['director']['engine_paid']


def test_claude_only_when_explicitly_chosen(client):
    gemini(client)
    project = client.post('/api/projects', json={'name': 'P', 'topic': 'Rom'}).json()
    client.put('/api/settings/claude', json={'api_key': 'sk-ant-synthetic-default-key-01'}, headers=SETTINGS)
    assert client.get(f'/api/projects/{project["id"]}/script').json()['default_provider'] == 'gemini'
    client.put('/api/settings/claude', json={'default_engine': True}, headers=SETTINGS)
    view = client.get(f'/api/projects/{project["id"]}/script').json()
    assert view['default_provider'] == 'claude' and view['director']['engine_paid']
    client.put('/api/settings/claude', json={'default_engine': False}, headers=SETTINGS)
    assert client.get(f'/api/projects/{project["id"]}/script').json()['default_provider'] == 'gemini'


def test_ollama_backup_is_offered_when_configured(client):
    gemini(client)
    client.put('/api/settings/ollama', json={'model': 'llama-test'}, headers=SETTINGS)
    project = client.post('/api/projects', json={'name': 'P', 'topic': 'Rom'}).json()
    director = client.get(f'/api/projects/{project["id"]}/script').json()['director']
    assert director['engine'] == 'gemini' and 'ollama' in director['backup_providers']
