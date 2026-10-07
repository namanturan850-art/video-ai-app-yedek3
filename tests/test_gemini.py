from contextlib import closing
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from app.database import initialize_database
from app.main import create_app
from app.providers.base import ScriptProvider, ScriptProviderError
from app.providers.factory import make_script_provider
from app.providers.gemini import API_ROOT, GeminiScriptProvider, GEMINI_TIMEOUT_MESSAGE, MODEL_LIST_TIMEOUT
from app.secret_store import SettingsStore
from app.settings import SettingsInputError

KEY = 'synthetic-gemini-key-only-1234'
MODEL = 'gemini-test-model'  # Mock fixture, not a claimed real or pinned model ID.
HEADERS = {'X-AI-Video-Studio': 'settings'}


def model_response(model=MODEL):
    return {'models': [{'name': 'models/' + model, 'supportedGenerationMethods': ['generateContent']}]}


def provider(handler, model=MODEL):
    return GeminiScriptProvider(KEY, model, transport=httpx.MockTransport(handler))


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        yield client


def install_mock(client, monkeypatch, handler):
    def factory(engine, settings, *, discovery=False):
        assert engine == 'gemini'
        config = settings.gemini_config()
        return GeminiScriptProvider(config.get('api_key', ''), '' if discovery else config['model'], transport=httpx.MockTransport(handler))
    monkeypatch.setattr('app.main.make_script_provider', factory)


def save(client, **overrides):
    # The key is saved first; model choices originate from a successful API discovery.
    response = client.put('/api/settings/gemini', json={'api_key': overrides.get('api_key', KEY)})
    assert response.status_code == 200, response.text
    service = client.app.state.settings
    service.record_gemini_models(service.gemini_config(), [MODEL])
    response = client.put('/api/settings/gemini', json={'model': overrides.get('model', MODEL)})
    assert response.status_code == 200, response.text
    return response


def test_gemini_is_optional_and_startup_offline(client, monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError('No automatic Gemini network call')
    monkeypatch.setattr('app.providers.gemini.GeminiScriptProvider._client', forbidden)
    assert client.get('/api/health').status_code == 200
    config = client.get('/api/settings').json()['gemini']
    assert config['status'] == 'Yapılandırılmadı'
    assert not config['has_api_key']
    assert config['model'] == ''
    assert not (tmp_path / 'data/secrets').exists()
    for engine in ('ollama', 'openai', 'gemini'):
        result = client.post('/api/projects', headers={'X-AI-Video-Studio': 'projects'}, json={'name': engine, 'topic': 'Test topic', 'script_engine': engine})
        assert result.status_code == 201
        assert result.json()['script_engine'] == engine


def test_key_encrypted_masked_and_preserved_after_restart(client, tmp_path):
    response = save(client, model='models/' + MODEL)
    assert KEY not in response.text
    config = response.json()['gemini']
    assert config['model'] == MODEL
    assert config['masked_api_key'] == '••••••••••1234'
    assert config['status'] == 'Hazır'
    assert 'api_key' not in config
    store = SettingsStore(tmp_path / 'data/secrets')
    assert KEY.encode() not in store.vault_path.read_bytes()
    assert store.read()['gemini']['api_key'] == KEY
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as restarted:
        assert restarted.get('/api/settings').json()['gemini']['masked_api_key'] == '••••••••••1234'
        assert KEY not in restarted.get('/api/settings').text
        assert KEY not in restarted.get('/api/diagnostics').text
    with closing(sqlite3.connect(tmp_path / 'data/app.db')) as connection:
        assert KEY not in '\n'.join(connection.iterdump())


def test_blank_key_keeps_saved_value_and_clear_only_gemini(client):
    save(client)
    client.put('/api/settings/pexels', json={'api_key': 'synthetic-pexels-5678'})
    response = client.put('/api/settings/gemini', json={'api_key': '', 'model': MODEL})
    assert response.json()['gemini']['has_api_key']
    response = client.delete('/api/settings/gemini')
    assert response.status_code == 200
    assert not response.json()['gemini']['has_api_key']
    assert response.json()['gemini']['model'] == ''
    assert response.json()['pexels']['has_api_key']


@pytest.mark.parametrize('payload', [
    {'api_key': 'short'}, {'api_key': KEY + '\n'}, {'api_key': 'ş' * 10},
    {'model': '../escape', 'api_key': KEY}, {'model': 'https://evil.example/model', 'api_key': KEY},
    {'model': 'model?key=' + KEY, 'api_key': KEY}, {'model': 123, 'api_key': KEY},
    {'base_url': 'https://evil.example', 'api_key': KEY}, {'api_key': KEY, 'model': KEY},
])
def test_invalid_settings_never_echo_secret(client, payload, tmp_path):
    response = client.put('/api/settings/gemini', json=payload)
    assert response.status_code == 422
    assert KEY not in response.text
    assert not (tmp_path / 'data/secrets/settings.enc').exists()


def test_key_as_model_partial_update_is_rejected(client):
    save(client)
    response = client.put('/api/settings/gemini', json={'model': KEY})
    assert response.status_code == 422
    assert KEY not in response.text
    assert client.get('/api/settings').json()['gemini']['model'] == MODEL


def test_damaged_vault_key_as_model_is_not_returned(client, tmp_path):
    store = SettingsStore(tmp_path / 'data/secrets')
    store.write({'gemini': {'api_key': KEY, 'model': KEY}})
    response = client.get('/api/settings')
    assert response.status_code == 200
    assert KEY not in response.text
    assert response.json()['gemini']['model'] == ''


def test_successful_connection_and_models_are_read_only(client, monkeypatch, caplog, capsys):
    save(client)
    requests = []
    def respond(request):
        requests.append(request)
        assert request.method == 'GET'
        assert request.url.host == 'generativelanguage.googleapis.com'
        assert request.url.path == '/v1beta/models'
        assert request.headers['x-goog-api-key'] == KEY
        assert KEY not in str(request.url)
        return httpx.Response(200, json=model_response())
    install_mock(client, monkeypatch, respond)
    caplog.set_level('DEBUG')
    response = client.post('/api/settings/gemini/test')
    assert response.status_code == 200
    assert response.json()['result']['status'] == 'Hazır'
    assert response.json()['models'] == [MODEL]
    assert response.json()['settings']['gemini']['status'] == 'Hazır'
    assert client.post('/api/settings/gemini/models').json()['models'] == [MODEL]
    assert len(requests) == 2
    assert KEY not in response.text
    assert KEY not in caplog.text
    assert KEY not in capsys.readouterr().out


def test_connection_with_key_without_model_offers_selection(client, monkeypatch):
    save(client, model='')
    install_mock(client, monkeypatch, lambda request: httpx.Response(200, json=model_response()))
    response = client.post('/api/settings/gemini/test')
    assert response.json()['models'] == [MODEL]
    assert 'model seçip kaydedin' in response.json()['result']['message']
    assert response.json()['settings']['gemini']['status'] == 'Yapılandırılmadı'


def test_missing_key_does_not_make_request(client, monkeypatch):
    install_mock(client, monkeypatch, lambda request: pytest.fail('No request with missing key'))
    response = client.post('/api/settings/gemini/test')
    assert response.json()['result']['status'] == 'Hata'
    assert 'API anahtarını kaydedin' in response.json()['result']['message']
    assert client.post('/api/settings/gemini/models').status_code == 422
    assert client.get('/api/health').status_code == 200


@pytest.mark.parametrize('status', [400, 401, 403, 404, 429, 500, 503])
def test_provider_error_bodies_never_leak(client, monkeypatch, caplog, status):
    save(client)
    install_mock(client, monkeypatch, lambda request: httpx.Response(status, json={'error': {'message': KEY}}))
    response = client.post('/api/settings/gemini/test')
    assert response.status_code == 200
    assert response.json()['result']['status'] == 'Hata'
    assert KEY not in response.text
    assert KEY not in client.get('/api/settings').text
    response = client.post('/api/settings/gemini/models')
    assert response.status_code >= 400
    assert KEY not in response.text
    assert KEY not in caplog.text


def test_pagination_and_supported_text_models_only():
    calls = []
    def respond(request):
        calls.append(request)
        assert request.url.params['pageSize'] == '1000'
        if 'pageToken' not in request.url.params:
            return httpx.Response(200, json={'models': [
                {'name': 'models/embedding-only', 'supportedGenerationMethods': ['embedContent']},
                {'name': 'models/' + MODEL, 'supportedGenerationMethods': ['generateContent'], 'displayName': KEY},
                {'name': 'models/' + KEY, 'supportedGenerationMethods': ['generateContent']},
            ], 'nextPageToken': 'page-two'})
        assert request.url.params['pageToken'] == 'page-two'
        return httpx.Response(200, json=model_response('gemini-other-test'))
    models = provider(respond).list_models()
    assert models == sorted([MODEL, 'gemini-other-test'])
    assert KEY not in str(models)
    assert all(KEY not in str(request.url) for request in calls)


@pytest.mark.parametrize('data', [
    {'models': 'invalid'}, {'models': ['invalid']}, {'models': [{'name': 'models/test', 'supportedGenerationMethods': 'generateContent'}]},
    {'models': []}, {'models': [{'name': 'models/bad/name', 'supportedGenerationMethods': ['generateContent']}]},
    {'models': [{'name': 'models/' + KEY, 'supportedGenerationMethods': ['generateContent']}]},
    {**model_response(), 'nextPageToken': KEY},
    {**model_response(), 'nextPageToken': ['invalid']},
])
def test_malformed_or_secret_contaminated_models_are_not_exposed(data):
    with pytest.raises(ScriptProviderError) as error:
        provider(lambda request: httpx.Response(200, json=data)).list_models()
    assert KEY not in str(error.value)


def test_repeated_page_token_is_bounded():
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={**model_response(), 'nextPageToken': 'same-page'})
    with pytest.raises(ScriptProviderError):
        provider(respond).list_models()
    assert len(requests) == 2


def test_redirect_does_not_forward_key():
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(302, headers={'Location': 'https://evil.example/?key=' + KEY})
    with pytest.raises(ScriptProviderError) as error:
        provider(respond).test_connection()
    assert len(calls) == 1
    assert calls[0].url.host == 'generativelanguage.googleapis.com'
    assert KEY not in str(error.value)


def test_timeout_is_safe():
    def respond(request):
        raise httpx.ReadTimeout(KEY, request=request)
    with pytest.raises(ScriptProviderError) as error:
        provider(respond).test_connection()
    assert KEY not in str(error.value)
    assert 'zamanında' in str(error.value)


def test_selected_model_missing_is_an_error(client, monkeypatch):
    save(client)
    install_mock(client, monkeypatch, lambda request: httpx.Response(200, json=model_response('gemini-other-test')))
    response = client.post('/api/settings/gemini/test')
    assert response.json()['result']['status'] == 'Hata'
    assert 'listesinde bulunamadı' in response.json()['result']['message']


def test_completed_generation_uses_official_contract_and_redacts_key(caplog):
    calls = []
    def respond(request):
        calls.append(request)
        assert request.method == 'POST'
        assert str(request.url) == API_ROOT + '/models/' + MODEL + ':generateContent'
        assert request.headers['x-goog-api-key'] == KEY
        body = json.loads(request.content)
        assert body['contents'] == [{'role': 'user', 'parts': [{'text': 'Write an original German story.'}]}]
        assert 'original' in body['systemInstruction']['parts'][0]['text']
        assert KEY not in request.content.decode()
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
            {'text': 'internal reasoning', 'thought': True}, {'text': 'Neue Geschichte.'}, {'text': KEY},
        ]}}]})
    gemini = provider(respond)
    assert isinstance(gemini, ScriptProvider)
    result = gemini.generate_script('Write an original German story.')
    assert 'Neue Geschichte.' in result
    assert '[gizlendi]' in result
    assert KEY not in result
    assert 'internal reasoning' not in result
    assert KEY not in repr(vars(gemini))
    assert KEY not in caplog.text
    assert len(calls) == 1


@pytest.mark.parametrize('data', [
    {'promptFeedback': {'blockReason': 'SAFETY'}},
    {'candidates': []}, {'candidates': [None]},
    {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': 'unfinished'}]}}]},
    {'candidates': [{'finishReason': 'SAFETY', 'content': {'parts': [{'text': KEY}]}}]},
    {'candidates': [{'finishReason': 'STOP', 'content': {'parts': []}}]},
    {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'private', 'thought': True}]}}]},
    {'candidates': [{'finishReason': 'STOP', 'content': {'parts': KEY}}]},
])
def test_unusable_or_incomplete_generation_is_rejected(data):
    with pytest.raises(ScriptProviderError) as error:
        provider(lambda request: httpx.Response(200, json=data)).generate_script('Original test prompt')
    assert KEY not in str(error.value)


@pytest.mark.parametrize('prompt', ['', ' ', KEY, 'x' * 100001])
def test_bad_prompt_does_not_make_network_call(prompt):
    with pytest.raises(ScriptProviderError):
        provider(lambda request: pytest.fail('No request')).generate_script(prompt)


def test_no_model_does_not_generate():
    with pytest.raises(ScriptProviderError):
        provider(lambda request: pytest.fail('No request'), model='').generate_script('Test')


def test_factory_returns_optional_gemini_and_no_silent_fallback(client):
    save(client)
    settings = client.app.state.settings
    gemini = make_script_provider('gemini', settings)
    assert isinstance(gemini, GeminiScriptProvider)
    assert isinstance(gemini, ScriptProvider)
    for engine in ('ollama', 'openai', 'unknown'):
        with pytest.raises(ScriptProviderError):
            make_script_provider(engine, settings)


def test_settings_changed_during_test_does_not_save_stale_result(client):
    save(client)
    service = client.app.state.settings
    snapshot = service.gemini_config()
    service.save('gemini', {'api_key': 'synthetic-replacement-key-5678'})
    with pytest.raises(SettingsInputError):
        service.record_gemini_test(snapshot, {'status': 'Hazır', 'message': 'Gemini API bağlantısı başarılı.'})
    assert 'last_test' not in service.gemini_config()


def test_gemini_mutations_require_origin_and_header(client):
    assert client.put('/api/settings/gemini', json={'api_key': KEY}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.post('/api/settings/gemini/models', headers={'Origin': 'null'}).status_code == 403
    assert client.get('/api/settings').headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('engine', ['ollama', 'openai', 'gemini'])
def test_project_engine_selection_persists(client, engine, tmp_path):
    response = client.post('/api/projects', headers={'X-AI-Video-Studio': 'projects'}, json={'name': 'Engine test', 'topic': 'Original topic', 'script_engine': engine})
    assert response.status_code == 201
    project = response.json()
    with TestClient(create_app(tmp_path / 'data')) as restarted:
        loaded = restarted.get('/api/projects/' + project['id']).json()
        assert loaded['script_engine'] == engine
        assert loaded['script_engine_label'].lower() == engine
    updated = client.patch('/api/projects/' + project['id'], headers={'X-AI-Video-Studio': 'projects'}, json={'script_engine': 'gemini'})
    assert updated.json()['script_engine'] == 'gemini'
    assert updated.json()['created_at'] == project['created_at']


def test_invalid_engine_rejected(client):
    response = client.post('/api/projects', headers={'X-AI-Video-Studio': 'projects'}, json={'name': 'test', 'topic': 'topic', 'script_engine': 'website-automation'})
    assert response.status_code == 422
    assert 'Senaryo motoru' in response.text


def test_part3_schema2_migration_preserves_existing_project(tmp_path):
    # Actual legacy layout without script_engine, independent of the new schema definition.
    fields = {
        'id': 'TEXT PRIMARY KEY', 'name': 'TEXT', 'topic': 'TEXT', 'reference_url': 'TEXT', 'language': 'TEXT',
        'target_duration_minutes': 'REAL', 'content_style': 'TEXT', 'min_scene_duration_seconds': 'REAL',
        'max_scene_duration_seconds': 'REAL', 'subtitles_enabled': 'INTEGER', 'background_music_enabled': 'INTEGER',
        'thumbnail_planning_enabled': 'INTEGER', 'status': 'TEXT', 'created_at': 'TEXT', 'updated_at': 'TEXT',
    }
    values = ['a' * 32, 'Legacy', 'Keep topic', '', 'de', 5, 'Hikâye', 4, 8, 1, 0, 1, 'draft', '2026-10-07T00:00:00+00:00', '2026-10-07T00:00:00+00:00']
    with closing(sqlite3.connect(tmp_path / 'app.db')) as connection, connection:
        connection.execute('CREATE TABLE app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        connection.execute("INSERT INTO app_metadata VALUES ('schema_version', '2')")
        connection.execute('CREATE TABLE projects (' + ', '.join(name + ' ' + kind for name, kind in fields.items()) + ')')
        connection.execute('INSERT INTO projects VALUES (' + ', '.join('?' for _ in values) + ')', values)
    store = SettingsStore(tmp_path / 'secrets')
    store.write({'pexels': {'api_key': 'legacy-fixture-only-5678'}})
    before = store.vault_path.read_bytes()
    initialize_database(tmp_path)
    initialize_database(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        project = client.get('/api/projects/' + 'a' * 32).json()
        assert project['name'] == 'Legacy'
        assert project['topic'] == 'Keep topic'
        assert project['script_engine'] == 'ollama'
        assert project['created_at'] == values[-2]
        assert client.get('/api/settings').json()['pexels']['has_api_key']
        assert not client.get('/api/settings').json()['gemini']['has_api_key']
        assert client.get('/api/health').status_code == 200
    assert store.vault_path.read_bytes() == before


def test_arbitrary_model_is_not_verified_or_saved_before_discovery(client):
    assert client.put('/api/settings/gemini', json={'api_key': KEY}).status_code == 200
    response = client.put('/api/settings/gemini', json={'model': 'as'})
    assert response.status_code == 422
    assert 'listeden geçerli bir model' in response.json()['message']
    config = client.get('/api/settings').json()['gemini']
    assert config['status'] == 'Yapılandırılmadı'
    assert not config['model_verified']
    assert config['model'] == ''


def test_discovery_repairs_legacy_placeholder_and_preserves_real_choices(client, monkeypatch, tmp_path):
    store = SettingsStore(tmp_path / 'data/secrets')
    store.write({'gemini': {'api_key': KEY, 'model': 'as'}})
    legacy = client.get('/api/settings').json()['gemini']
    assert legacy['status'] == 'Yapılandırılmadı'
    assert not legacy['model_verified']
    install_mock(client, monkeypatch, lambda request: httpx.Response(200, json=model_response()))
    discovery = client.post('/api/settings/gemini/models')
    assert discovery.status_code == 200
    config = discovery.json()['settings']['gemini']
    assert config['models'] == [MODEL]
    assert config['status'] == 'Hata'
    assert 'listesinde bulunamadı' in config['message']
    assert not config['model_verified']
    assert client.put('/api/settings/gemini', json={'model': 'as'}).status_code == 422
    response = client.put('/api/settings/gemini', json={'model': MODEL})
    assert response.json()['gemini']['model_verified']
    with TestClient(create_app(tmp_path / 'data')) as restarted:
        assert restarted.get('/api/settings').json()['gemini']['models'] == [MODEL]
        assert restarted.get('/api/settings').json()['gemini']['model_verified']


def test_model_discovery_ignores_malformed_legacy_model(client, monkeypatch, tmp_path):
    store = SettingsStore(tmp_path / 'data/secrets')
    store.write({'gemini': {'api_key': KEY, 'model': '../old-placeholder'}})
    install_mock(client, monkeypatch, lambda request: httpx.Response(200, json=model_response()))
    response = client.post('/api/settings/gemini/models')
    assert response.status_code == 200
    assert response.json()['models'] == [MODEL]
    assert not response.json()['settings']['gemini']['model_verified']


@pytest.mark.parametrize('saved_model', ['as', '../old-placeholder'])
def test_invalid_saved_model_connection_still_returns_real_models(client, monkeypatch, tmp_path, saved_model):
    SettingsStore(tmp_path / 'data/secrets').write({'gemini': {'api_key': KEY, 'model': saved_model}})
    install_mock(client, monkeypatch, lambda request: httpx.Response(200, json=model_response()))
    response = client.post('/api/settings/gemini/test')
    assert response.json()['result']['category'] == 'model_unavailable'
    assert response.json()['result']['status'] == 'Hata'
    assert response.json()['models'] == [MODEL]
    assert response.json()['settings']['gemini']['models'] == [MODEL]
    assert not response.json()['settings']['gemini']['model_verified']


def test_changed_key_clears_old_model_verification(client):
    save(client)
    response = client.put('/api/settings/gemini', json={'api_key': 'synthetic-new-key-5678'})
    config = response.json()['gemini']
    assert config['models'] == []
    assert not config['model_verified']
    assert config['model'] == ''
    assert config['status'] == 'Yapılandırılmadı'


def test_key_changed_during_discovery_does_not_cache_another_keys_models(client):
    save(client)
    service = client.app.state.settings
    original = service.gemini_config()
    service.save('gemini', {'api_key': 'synthetic-replacement-5678'})
    with pytest.raises(SettingsInputError):
        service.record_gemini_models(original, [MODEL])
    assert client.get('/api/settings').json()['gemini']['models'] == []


def test_backend_discovery_can_take_more_than_twenty_seconds(monkeypatch):
    clock = [0]
    monkeypatch.setattr('app.providers.gemini.time', SimpleNamespace(monotonic=lambda: clock[0]))
    def respond(request):
        assert request.extensions['timeout']['read'] > 20
        assert request.extensions['timeout']['connect'] > 20
        clock[0] += 25  # Virtual seconds; no blocking wait or real Google call.
        return httpx.Response(200, json=model_response())
    assert provider(respond).list_models() == [MODEL]


def test_backend_model_list_total_budget_is_bounded(monkeypatch):
    clock = [0]
    monkeypatch.setattr('app.providers.gemini.time', SimpleNamespace(monotonic=lambda: clock[0]))
    def respond(request):
        clock[0] += MODEL_LIST_TIMEOUT + 1
        return httpx.Response(200, json=model_response())
    with pytest.raises(ScriptProviderError) as error:
        provider(respond).list_models()
    assert error.value.category == 'gemini_timeout'
    assert str(error.value) == GEMINI_TIMEOUT_MESSAGE


@pytest.mark.parametrize('operation', ['models', 'test'])
@pytest.mark.parametrize('error_type, category', [(httpx.ReadTimeout, 'gemini_timeout'), (httpx.ConnectError, 'no_internet'), (httpx.ProxyError, 'no_internet')])
def test_gemini_network_failure_categories_are_safe(client, monkeypatch, caplog, operation, error_type, category):
    save(client)
    def respond(request):
        raise error_type('private Google details: ' + KEY, request=request)
    install_mock(client, monkeypatch, respond)
    caplog.set_level('INFO')
    response = client.post('/api/settings/gemini/' + operation)
    result = response.json()['result'] if operation == 'test' else response.json()
    assert result['category'] == category
    if category == 'gemini_timeout':
        assert result['message'] == GEMINI_TIMEOUT_MESSAGE
    else:
        assert 'internet bağlantısı kurulamadı' in result['message']
    assert 'Uygulamaya ulaşılamadı' not in response.text
    assert KEY not in response.text
    assert KEY not in caplog.text
    assert 'private Google details' not in caplog.text
    assert 'category=' + category in caplog.text
    assert 'result=failure' in caplog.text
    assert client.get('/api/health').status_code == 200


@pytest.mark.parametrize('status, category', [(403, 'key_rejected'), (429, 'quota_limit'), (503, 'upstream_error')])
def test_gemini_api_rejection_has_safe_category_and_log(client, monkeypatch, caplog, status, category):
    save(client)
    install_mock(client, monkeypatch, lambda request: httpx.Response(status, json={'error': {'message': KEY + ' Google raw body'}}))
    caplog.set_level('INFO')
    response = client.post('/api/settings/gemini/models')
    assert response.json()['category'] == category
    assert KEY not in response.text + caplog.text
    assert 'Google raw body' not in response.text + caplog.text
    assert 'operation=list_models result=failure category=' + category in caplog.text
    assert 'elapsed_ms=' in caplog.text


@pytest.mark.parametrize('method, suffix', [('post', '/models'), ('post', '/test'), ('put', ''), ('delete', '')])
def test_unexpected_gemini_backend_exception_returns_safe_json_not_reset(client, monkeypatch, caplog, method, suffix):
    save(client)
    def explode(*args, **kwargs):
        raise RuntimeError(KEY + ' raw Google response and private traceback')
    if suffix:
        monkeypatch.setattr('app.main.make_script_provider', explode)
    else:
        monkeypatch.setattr(client.app.state.settings.store, 'write', explode)
    caplog.set_level('INFO')
    # raise_server_exceptions is True: this fails if the middleware re-raises.
    response = getattr(client, method)('/api/settings/gemini' + suffix, **({'json': {'model': MODEL}} if method == 'put' else {}))
    assert response.status_code == 500
    assert response.headers['content-type'] == 'application/json'
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['category'] == 'unexpected_backend'
    assert 'beklenmeyen bir sunucu hatası' in response.json()['message']
    assert KEY not in response.text + caplog.text
    assert 'raw Google response' not in response.text + caplog.text
    assert 'Traceback' not in caplog.text
    assert 'result=failure category=unexpected_backend' in caplog.text
    assert client.get('/api/health').status_code == 200


def test_gemini_success_logging_has_only_safe_diagnostics(client, monkeypatch, caplog):
    save(client)
    install_mock(client, monkeypatch, lambda request: httpx.Response(200, json=model_response()))
    caplog.set_level('INFO')
    assert client.post('/api/settings/gemini/models').status_code == 200
    assert client.post('/api/settings/gemini/test').json()['result']['status'] == 'Hazır'
    records = [record.getMessage() for record in caplog.records if record.name.endswith('gemini_settings')]
    assert len(records) == 2
    assert all('result=success category=none elapsed_ms=' in message for message in records)
    assert KEY not in caplog.text
    assert MODEL not in '\n'.join(records)
