"""PR-A: Claude connection, encrypted/masked key, free test, cost ledger, backup offer.

The Anthropic client is an in-memory fake: no network call and no cost.
"""
from contextlib import closing
import json
import sqlite3

import anthropic
import pytest
from fastapi.testclient import TestClient

from app.ai_usage import estimate, UsageLedger
from app.database import initialize_database, SCHEMA_VERSION
from app.main import create_app
from app.providers.base import ScriptProviderError
from app.providers.claude import ClaudeProvider, FALLBACK_BETA
from fake_anthropic import FakeAnthropic, api_error, message
from test_scripts import FakeProvider, HEADERS

CLAUDE_KEY = 'sk-ant-synthetic-claude-key-0042'
SETTINGS_HEADERS = {'X-AI-Video-Studio': 'settings'}


@pytest.fixture
def app_client(tmp_path):
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        yield client, tmp_path / 'data'


def save_claude(client, **extra):
    r = client.put('/api/settings/claude', json={'api_key': CLAUDE_KEY, **extra}, headers=SETTINGS_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def test_key_is_encrypted_masked_and_never_returned(app_client):
    client, data = app_client
    view = save_claude(client, model='claude-sonnet-5-5')['claude']
    assert view['has_api_key'] and view['masked_api_key'].endswith(CLAUDE_KEY[-4:]) and CLAUDE_KEY not in json.dumps(view)
    assert view['model'] == 'claude-sonnet-5-5' and [m['id'] for m in view['models']] == ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5']
    assert CLAUDE_KEY not in client.get('/api/settings').text
    for path in data.rglob('*'):
        if path.is_file(): assert CLAUDE_KEY.encode() not in path.read_bytes(), path  # vault is encrypted at rest


def test_invalid_model_is_rejected(app_client):
    client, _ = app_client
    r = client.put('/api/settings/claude', json={'model': 'gpt-4o'}, headers=SETTINGS_HEADERS)
    assert r.status_code == 422 and 'Model' in r.json()['message']


def test_connection_test_is_free_and_reports_plain_turkish(app_client, monkeypatch):
    client, _ = app_client; save_claude(client)
    fake = FakeAnthropic()
    monkeypatch.setattr('app.providers.claude._client', lambda key: fake)
    r = client.post('/api/settings/claude/test', headers=SETTINGS_HEADERS).json()
    assert r['result']['status'] == 'Hazır' and 'ücretsiz' in r['result']['message'] and not fake.requests
    assert r['settings']['claude']['status'] == 'Hazır'
    fake._model_error = api_error(anthropic.AuthenticationError, 401)
    r = client.post('/api/settings/claude/test', headers=SETTINGS_HEADERS).json()
    assert r['result']['status'] == 'Hata' and 'anahtarı kabul edilmedi' in r['result']['message'] and CLAUDE_KEY not in json.dumps(r)


def test_requests_use_chosen_model_fallbacks_and_effort():
    fake = FakeAnthropic()
    provider = ClaudeProvider(CLAUDE_KEY, 'claude-sonnet-5-5', client=fake)
    assert provider.generate_script('TASK: section\nWrite.') == 'Hallo Welt.'
    request = fake.requests[0]
    assert request['model'] == 'claude-sonnet-5-5' and request['betas'] == [FALLBACK_BETA] and request['fallbacks'] == 'default'
    assert request['output_config'] == {'effort': 'high'} and 'thinking' not in request and 'temperature' not in request


@pytest.mark.parametrize('error,category', [
    (api_error(anthropic.AuthenticationError, 401), 'key_rejected'), (api_error(anthropic.PermissionDeniedError, 403), 'key_rejected'),
    (api_error(anthropic.NotFoundError, 404), 'model_unavailable'), (api_error(anthropic.RateLimitError, 429), 'rate_limit'),
    (api_error(anthropic.BadRequestError, 400, 'Your credit balance is too low'), 'billing_quota'),
    (api_error(anthropic.BadRequestError, 400, 'invalid'), 'invalid_request'),
    (api_error(anthropic.InternalServerError, 529), 'upstream_error'),
    (api_error(anthropic.APIConnectionError, 0), 'no_internet'), (api_error(anthropic.APITimeoutError, 0), 'generation_timeout')])
def test_errors_map_to_plain_categories_without_leaking(error, category):
    provider = ClaudeProvider(CLAUDE_KEY, 'claude-opus-5-5', client=FakeAnthropic(lambda r: error))
    with pytest.raises(ScriptProviderError) as raised: provider.generate_script('TASK: x\nhi')
    assert raised.value.category == category and CLAUDE_KEY not in str(raised.value) and 'synthetic' not in str(raised.value)


@pytest.mark.parametrize('stop,category', [('refusal', 'refusal'), ('max_tokens', 'incomplete_response')])
def test_refusal_and_truncation_are_errors_not_empty_success(stop, category, tmp_path):
    projects = SimpleProjects(tmp_path)
    ledger = UsageLedger(projects)
    provider = ClaudeProvider(CLAUDE_KEY, 'claude-opus-5-5', client=FakeAnthropic(lambda r: message('partial', stop_reason=stop)), ledger=ledger)
    with pytest.raises(ScriptProviderError) as raised: provider.generate_script('TASK: x\nhi')
    assert raised.value.category == category
    with closing(projects._connection()) as c: assert c.execute('SELECT COUNT(*) FROM ai_usage').fetchone()[0] == 1


def test_json_output_uses_schema_and_records_cost(tmp_path):
    projects = SimpleProjects(tmp_path); ledger = UsageLedger(projects)
    fake = FakeAnthropic(lambda r: message('{"answer": 42}', input_tokens=2000, output_tokens=1000))
    provider = ClaudeProvider(CLAUDE_KEY, 'claude-opus-5-5', client=fake, ledger=ledger)
    schema = {'type': 'object', 'properties': {'answer': {'type': 'integer'}}, 'required': ['answer'], 'additionalProperties': False}
    assert provider.complete_json('plan', 'Answer.', schema, effort='low') == {'answer': 42}
    assert fake.requests[0]['output_config'] == {'effort': 'low', 'format': {'type': 'json_schema', 'schema': schema}}
    assert ledger.project_summary(None)['items'] == []  # unattributed calls are kept but not shown in a project
    with closing(projects._connection()) as c:
        assert c.execute('SELECT cost_usd FROM ai_usage').fetchone()[0] == pytest.approx(estimate('claude-opus-5-5', 2000, 1000))


def test_cost_estimate_uses_list_prices():
    assert estimate('claude-opus-5-5', 1_000_000, 0) == 4.0 and estimate('claude-opus-5-5', 0, 1_000_000) == 20.0
    assert estimate('claude-sonnet-5-5', 1_000_000, 1_000_000) == 12.0 and estimate('claude-haiku-5-5', 1_000_000, 0) == .1
    assert estimate('claude-opus-5-5', 0, 0, cache_read=1_000_000) == pytest.approx(.4)


def test_saving_a_claude_key_alone_never_makes_the_paid_engine_default(app_client):
    client, _ = app_client; save_claude(client)
    project = client.post('/api/projects', json={'name': 'P', 'topic': 'Rom', 'target_duration_minutes': 2}).json()
    director = client.get(f'/api/projects/{project["id"]}/script').json()['director']
    assert not director['claude_default'] and director['engine'] is None and not director['engine_paid']
    settings = client.app.state.settings
    settings.save('gemini', {'api_key': 'synthetic-gemini-key-5555'}); settings.record_gemini_models(settings.gemini_config(), ['gemini-x']); settings.save('gemini', {'model': 'gemini-x'})
    director = client.get(f'/api/projects/{project["id"]}/script').json()['director']
    assert director['engine'] == 'gemini' and not director['engine_paid']
    save_claude(client, default_engine=True)
    assert client.get(f'/api/projects/{project["id"]}/script').json()['director']['engine'] == 'claude'


def test_claude_script_job_end_to_end_with_project_cost(app_client, monkeypatch):
    client, _ = app_client; save_claude(client, default_engine=True)
    script = FakeProvider()
    fake = FakeAnthropic(lambda request: message(script.generate_script(request['messages'][0]['content']), input_tokens=3000, output_tokens=800))
    monkeypatch.setattr('app.providers.claude._client', lambda key: fake)
    project = client.post('/api/projects', json={'name': 'Claude', 'topic': 'Bermuda-Dreieck', 'script_engine': 'gemini', 'target_duration_minutes': 2}).json()
    view = client.get(f'/api/projects/{project["id"]}/script').json()
    assert view['default_provider'] == 'claude' and view['director']['claude_default']
    r = client.post(f'/api/projects/{project["id"]}/script/generate', json={'provider': 'claude'})
    assert r.status_code == 202, r.text
    client.app.state.scripts.futures[r.json()['job_id']].result(timeout=10)
    view = client.get(f'/api/projects/{project["id"]}/script').json()
    assert view['current'] and view['current']['provider'] == 'claude' and fake.requests
    usage = client.get(f'/api/projects/{project["id"]}/ai-usage').json()
    assert usage['total_calls'] == len(fake.requests) and usage['total_cost_usd'] == pytest.approx(round(len(fake.requests) * estimate('claude-opus-5-5', 3000, 800), 4), abs=1e-3)
    assert CLAUDE_KEY not in json.dumps(usage)


def test_claude_failure_offers_only_configured_backups_never_switches(app_client, monkeypatch):
    client, _ = app_client; save_claude(client)
    client.put('/api/settings/ollama', json={'model': 'llama-test'}, headers=SETTINGS_HEADERS)
    fake = FakeAnthropic(lambda r: api_error(anthropic.RateLimitError, 429))
    monkeypatch.setattr('app.providers.claude._client', lambda key: fake)
    project = client.post('/api/projects', json={'name': 'X', 'topic': 'Rom', 'target_duration_minutes': 2}).json()
    r = client.post(f'/api/projects/{project["id"]}/script/generate', json={'provider': 'claude'})
    client.app.state.scripts.futures[r.json()['job_id']].result(timeout=10)
    view = client.get(f'/api/projects/{project["id"]}/script').json()
    assert view['job']['status'] == 'error' and view['job']['provider'] == 'claude' and not view['current']
    assert view['director']['backup_providers'] == ['ollama']  # offered, not used


def test_schema_11_migration_is_additive_and_keeps_projects(tmp_path):
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        pid = client.post('/api/projects', json={'name': 'Alt', 'topic': 'Alt'}).json()['id']
    database = tmp_path / 'data' / 'app.db'
    with closing(sqlite3.connect(database)) as c, c:  # simulate an owner database still at schema 10
        c.execute('DROP TABLE ai_usage'); c.execute("UPDATE app_metadata SET value='10' WHERE key='schema_version'")
    initialize_database(tmp_path / 'data')
    with closing(sqlite3.connect(database)) as c:
        assert c.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] == SCHEMA_VERSION == '12'
        assert c.execute('SELECT name FROM projects WHERE id=?', (pid,)).fetchone()[0] == 'Alt'
        assert c.execute("SELECT 1 FROM sqlite_master WHERE name='ai_usage'").fetchone()


class SimpleProjects:
    def __init__(self, root):
        from threading import RLock
        self.lock = RLock(); self.database = initialize_database(root / 'db')
    def _connection(self):
        return sqlite3.connect(self.database)
