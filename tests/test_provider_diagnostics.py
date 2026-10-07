"""Mocked regression evidence only. Live provider test must be run by owner on Windows."""
from contextlib import closing
import json
import sqlite3
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.base import ScriptProviderError
from app.providers.gemini import GeminiScriptProvider
from app.providers.json_output import parse_json_object
from app.providers.text_api import OllamaScriptProvider, OpenAIScriptProvider
from app.provider_diagnostics import PROVIDERS, TESTS, MESSAGES
from app.scripts.engine import SecretGuard, YouTubeScriptEngine
from app.scripts.models import ConceptBlueprint, ScriptError, ScriptOptions
from app.secret_store import SettingsStore, SettingsStorageError

KEY = 'synthetic-diagnostic-gemini-secret-1234'
OTHER_KEY = 'synthetic-diagnostic-openai-secret-5678'
MODEL = 'diagnostic-model'
OLLAMA_MODEL = 'qwen3.5:9b'
HEADERS = {'X-AI-Video-Studio': 'settings'}
URL = '/api/settings/ai-diagnostics'
NARRATION = 'Çalışma masanızı düzenlemek için önce kullanmadığınız eşyaları kaldırın. Sık kullandığınız malzemeleri kolay ulaşabileceğiniz bir yere koyun. Böylece günlük işlerinize başlamadan önce ihtiyacınız olanları daha kolay bulabilirsiniz.'


@pytest.fixture
def diagnostic(tmp_path):
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        settings = client.app.state.settings
        settings.save('gemini', {'api_key': KEY})
        settings.record_gemini_models(settings.gemini_config(), [MODEL])
        settings.save('gemini', {'model': MODEL})
        settings.save('openai', {'enabled': True, 'api_key': OTHER_KEY, 'model': MODEL})
        settings.save('ollama', {'base_url': 'http://127.0.0.1:11434', 'model': OLLAMA_MODEL})
        calls = []
        def respond(request):
            calls.append(request)
            if request.method == 'GET':
                if request.url.host == 'generativelanguage.googleapis.com':
                    return httpx.Response(200, json={'models': [{'name': 'models/' + MODEL, 'supportedGenerationMethods': ['generateContent']}]})
                if request.url.host == 'api.openai.com':
                    return httpx.Response(200, json={'id': MODEL})
                return httpx.Response(200, json={'models': [{'name': OLLAMA_MODEL}]})
            body = json.loads(request.content)
            prompt = body['contents'][0]['parts'][0]['text'] if 'contents' in body else body['messages'][-1]['content'] if 'messages' in body else body['prompt']
            assert KEY not in prompt and OTHER_KEY not in prompt
            text = 'TEST_OK' if prompt.startswith('Return only TEST_OK') else 'Here is the JSON:\n```json\n{"status":"ok"}\n```\nDone.' if prompt.startswith('TASK: diagnostic_json') else NARRATION
            if 'contents' in body:
                return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': text}]}}]})
            if 'messages' in body:
                return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': text}}]})
            assert body['stream'] is False and body['think'] is False and 'think' not in body.get('options', {})
            return httpx.Response(200, json={'response': text, 'done': True, 'done_reason': 'stop'})
        install_transport(client, httpx.MockTransport(respond))
        yield client, calls, respond


def install_transport(client, transport):
    def factory(provider, settings):
        config = settings.script_config(provider)
        if provider == 'gemini': return GeminiScriptProvider(config.get('api_key', ''), config['model'], transport=transport)
        if provider == 'ollama': return OllamaScriptProvider(config['base_url'], config['model'], transport=transport)
        if not config['enabled']: raise ScriptProviderError('private ignored text', category='provider_disabled')
        return OpenAIScriptProvider(config.get('api_key', ''), config['model'], transport=transport)
    client.app.state.ai_diagnostics.provider_factory = factory


def check(client, provider, test):
    response = client.post(f'{URL}/{provider}/{test}', json={'cost_confirmed': True})
    assert response.status_code == 202, response.text
    client.app.state.ai_diagnostics.futures[provider].result(timeout=5)
    report = client.get(URL)
    assert report.headers['cache-control'] == 'no-store'
    assert KEY not in report.text and OTHER_KEY not in report.text
    return next(item for item in report.json()['providers'] if item['provider'] == provider)


@pytest.mark.parametrize('provider', PROVIDERS)
def test_five_separate_checks_use_real_adapters_and_one_section(diagnostic, provider, caplog):
    client, calls, _ = diagnostic
    caplog.set_level('INFO')
    for test in TESTS:
        view = check(client, provider, test)
        assert view[test + '_status'] == 'Başarılı', view
    assert len(calls) == 4  # Storage: no network. Connection + three independent tiny requests.
    assert calls[0].method == 'GET'
    section_body = json.loads(calls[-1].content)
    assert 'TASK: section' in str(section_body) and 'target_words' in str(section_body)
    assert 'TASK: concept' not in str(section_body) and 'TASK: plan' not in str(section_body)
    assert NARRATION not in json.dumps(view) + caplog.text
    assert KEY not in caplog.text and OTHER_KEY not in caplog.text and 'Authorization' not in caplog.text
    for test in TESTS:
        assert 'operation=' + test in caplog.text
        assert view['tests'][test]['elapsed_ms'] >= 0
    settings = view['tests']['settings']
    assert settings['model'] == (OLLAMA_MODEL if provider == 'ollama' else MODEL)
    if provider != 'ollama': assert settings['has_api_key'] and settings['masked_api_key'].endswith('1234' if provider == 'gemini' else '5678')
    if provider == 'openai': assert settings['enabled'] is True


def test_settings_save_reopen_preserves_all_credentials_projects_and_scripts(diagnostic):
    client, calls, _ = diagnostic
    settings = client.app.state.settings
    settings.save('ai33', {'api_key': 'synthetic-ai33-preserved-secret-9012'})
    project = client.post('/api/projects', headers={'X-AI-Video-Studio': 'projects'}, json={'name': 'Korunacak', 'topic': 'Düzen'}).json()
    client.app.state.scripts.repository.create_version(project['id'], NARRATION, 'ollama', OLLAMA_MODEL,
        ScriptOptions(provider='ollama').model_dump(), 'Kısa açıklama', {'consistent': True, 'issues': []})
    before = settings.store.read()
    with closing(sqlite3.connect(client.app.state.database)) as db: database = '\n'.join(db.iterdump())
    folder = client.app.state.projects.root / project['id'] if hasattr(client.app.state.projects, 'root') else settings.store.directory.parent / 'projects' / project['id']
    files = {path.relative_to(folder): path.read_bytes() for path in folder.rglob('*') if path.is_file()}
    for provider in PROVIDERS: assert check(client, provider, 'settings')['settings_status'] == 'Başarılı'
    assert SettingsStore(settings.store.directory).read() == before
    assert not calls
    with closing(sqlite3.connect(client.app.state.database)) as db: assert '\n'.join(db.iterdump()) == database
    assert {path.relative_to(folder): path.read_bytes() for path in folder.rglob('*') if path.is_file()} == files
    with TestClient(create_app(settings.store.directory.parent), headers=HEADERS) as restarted:
        public = restarted.get('/api/settings').json()
        assert public['gemini']['has_api_key'] and public['openai']['enabled'] and public['openai']['model'] == MODEL
        assert all(item['settings_status'] == 'Bekliyor' for item in restarted.get(URL).json()['providers'])
        assert restarted.get('/api/projects/' + project['id']).status_code == 200


@pytest.mark.parametrize('category', ['key_decrypt_failed', 'folder_permission', 'temp_file_failed', 'atomic_replace_failed', 'encryption_failed', 'storage_locked'])
def test_storage_failure_is_separate_and_blocks_api_without_reset(diagnostic, monkeypatch, category):
    client, calls, _ = diagnostic
    store = client.app.state.settings.store
    before_key, before_vault = store.key_path.read_bytes(), store.vault_path.read_bytes()
    def fail(values): raise SettingsStorageError(KEY + ' raw error', category=category)
    monkeypatch.setattr(store, 'write', fail)
    view = check(client, 'openai', 'settings')
    assert view['settings_status'] == 'Ayar kaydetme hatası' and view['safe_error_category'] == category
    assert check(client, 'openai', 'connection')['safe_error_category'] == 'settings_required'
    assert not calls and store.key_path.read_bytes() == before_key and store.vault_path.read_bytes() == before_vault


def test_settings_changed_requires_storage_recheck_without_api(diagnostic):
    client, calls, _ = diagnostic
    check(client, 'openai', 'settings')
    client.put('/api/settings/openai', json={'model': 'changed-model'})
    view = check(client, 'openai', 'simple_generation')
    assert view['safe_error_category'] == 'settings_changed' and view['settings_status'] == 'Hata'
    assert not calls


def test_settings_verification_uses_new_reader_not_cached_safe_status(diagnostic, monkeypatch):
    client, calls, _ = diagnostic
    store = client.app.state.settings.store
    before = store.read()
    class WrongReader:
        def __init__(self, directory): assert directory == store.directory
        def read(self): return {'openai': {'enabled':False}}
    monkeypatch.setattr('app.provider_diagnostics.SettingsStore', WrongReader)
    view = check(client, 'openai', 'settings')
    assert view['settings_status'] == 'Ayar kaydetme hatası' and view['safe_error_category'] == 'settings_reopen_mismatch'
    assert store.read() == before and not calls


@pytest.mark.parametrize('enabled,key,category', [(False, OTHER_KEY, 'provider_disabled'), (True, '', 'missing_key')])
def test_openai_storage_success_does_not_mask_disabled_or_missing_key(diagnostic, enabled, key, category):
    client, calls, _ = diagnostic
    config = client.app.state.settings.store.read(); config['openai'].update(enabled=enabled, api_key=key); client.app.state.settings.store.write(config)
    storage = check(client, 'openai', 'settings')
    assert storage['settings_status'] == 'Başarılı' and storage['tests']['settings']['enabled'] is enabled
    assert check(client, 'openai', 'connection')['safe_error_category'] == category
    assert not calls


@pytest.mark.parametrize('status,body,category,result', [
    (401, {'error': {'message': KEY}}, 'key_rejected', 'Hata'),
    (404, {'error': {'message': KEY}}, 'model_unavailable', 'Model uyumsuz'),
    (429, {'error': {'message': KEY}}, 'quota_limit', 'Kota sınırı'),
    (429, {'error': {'details': [{'@type':'type.googleapis.com/google.rpc.QuotaFailure', 'violations':[{'quotaId':'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaMetric':'generate_content_free_tier_requests'}]}]}}, 'free_quota_exhausted', 'Kota sınırı'),
    (429, {'error': {'details': [{'@type':'type.googleapis.com/google.rpc.QuotaFailure', 'violations':[{'quotaId':'GenerateRequestsPerMinutePerProjectPerModel', 'quotaMetric':'generate_content_requests'}]}]}}, 'rate_limit', 'Kota sınırı'),
    (400, {'error': {'details':[{'@type':'type.googleapis.com/google.rpc.ErrorInfo', 'reason':'API_KEY_INVALID'}]}}, 'key_rejected', 'Hata'),
    (400, {'error': {'status':'INVALID_ARGUMENT', 'message':KEY}}, 'invalid_request', 'Hata'),
    (200, {'candidates': [{'finishReason':'STOP','content':{'parts':[]}}]}, 'empty_response', 'Yanıt biçimi hatası'),
    (200, {'raw_response':KEY}, 'invalid_response', 'Yanıt biçimi hatası'),
])
def test_gemini_generation_failure_layer_does_not_change_connection(diagnostic, status, body, category, result, caplog):
    client, calls, respond = diagnostic
    check(client, 'gemini', 'settings'); check(client, 'gemini', 'connection')
    caplog.set_level('INFO')
    def faulty(request):
        if request.method == 'GET': return respond(request)
        calls.append(request)
        return httpx.Response(status, json=body, headers={'Retry-After': '1'})
    install_transport(client, httpx.MockTransport(faulty))
    view = check(client, 'gemini', 'simple_generation')
    assert view['simple_generation_status'] == result and view['safe_error_category'] == category
    assert view['connection_status'] == 'Başarılı'
    assert KEY not in caplog.text and 'Traceback' not in caplog.text
    if status == 429:
        count = len(calls)
        assert check(client, 'gemini', 'json')['json_status'] == 'Kota sınırı'
        assert len(calls) == count  # No immediate repeat, no full engine/fallback.
    assert client.get('/api/health').status_code == 200


@pytest.mark.parametrize('error_type,category', [(httpx.ReadTimeout,'gemini_timeout'), (httpx.ConnectError,'no_internet')])
def test_timeout_and_internet_failure_do_not_report_local_app_down(diagnostic, error_type, category):
    client, _, _ = diagnostic
    check(client, 'gemini', 'settings')
    def fail(request): raise error_type(KEY, request=request)
    install_transport(client, httpx.MockTransport(fail))
    view = check(client, 'gemini', 'simple_generation')
    assert view['safe_error_category'] == category and view['simple_generation_status'] == 'Bağlantı hatası'
    assert 'Uygulamaya ulaşılamadı' not in view['safe_message']
    if category == 'gemini_timeout': assert view['safe_message'] == MESSAGES['gemini_timeout']


@pytest.mark.parametrize('provider', PROVIDERS)
def test_broken_http_transport_is_not_json_format_failure(diagnostic, provider):
    client, _, _ = diagnostic
    check(client,provider,'settings')
    def broken(request): raise httpx.RemoteProtocolError(KEY + ' private transport details')
    install_transport(client,httpx.MockTransport(broken))
    view = check(client,provider,'simple_generation')
    assert view['simple_generation_status'] == 'Bağlantı hatası' and view['safe_error_category'] == 'network_error'


@pytest.mark.parametrize('status,code,category', [(401,None,'key_rejected'),(404,'model_not_found','model_unavailable'),(400,None,'invalid_model'),(429,'insufficient_quota','billing_quota'),(429,'rate_limit_exceeded','rate_limit'),(500,None,'upstream_error')])
def test_openai_storage_connection_and_generation_are_separate(diagnostic, status, code, category):
    client, calls, respond = diagnostic
    check(client,'openai','settings'); check(client,'openai','connection')
    def reject(request):
        if request.method == 'GET': return respond(request)
        calls.append(request)
        return httpx.Response(status,json={'error':{'code':code,'message':OTHER_KEY}},headers={'Retry-After':'1'})
    install_transport(client,httpx.MockTransport(reject))
    view = check(client,'openai','simple_generation')
    assert view['settings_status'] == 'Başarılı' and view['connection_status'] == 'Başarılı'
    assert view['safe_error_category'] == category
    assert view['tests']['simple_generation']['upstream_http_status'] == status


@pytest.mark.parametrize('text,category', [('not JSON','invalid_json'), ('{"status":','invalid_json'), ('{}','schema_invalid'), ('{"status":"wrong"}','schema_invalid')])
def test_ollama_json_parse_and_schema_failures_are_visible(diagnostic,text,category):
    client, _, _ = diagnostic
    check(client,'ollama','settings')
    install_transport(client,httpx.MockTransport(lambda request:httpx.Response(200,json={'response':text,'done':True})))
    view = check(client,'ollama','json')
    assert view['json_status'] == 'Yanıt biçimi hatası' and view['safe_error_category'] == category
    assert text not in view['safe_message']


def test_wrong_gemini_saved_model_has_model_layer_not_storage_error(diagnostic):
    client, _, _ = diagnostic
    values = client.app.state.settings.store.read(); values['gemini']['model']='old-placeholder'; client.app.state.settings.store.write(values)
    assert check(client,'gemini','settings')['settings_status'] == 'Başarılı'
    view = check(client,'gemini','connection')
    assert view['connection_status'] == 'Model uyumsuz' and view['safe_error_category'] == 'model_unavailable'


def test_live_checks_only_run_when_clicked_and_cloud_cost_confirmed(diagnostic):
    client, calls, _ = diagnostic
    assert client.get('/settings/ai-diagnostics').status_code == 200
    report = client.get(URL).json()
    assert all(item['simple_generation_status'] == 'Bekliyor' for item in report['providers']) and not calls
    assert client.post(URL + '/openai/json', json={}).status_code == 422
    assert client.post(URL + '/gemini/json', json={'cost_confirmed': 'yes'}).status_code == 422
    assert client.post(URL + '/ollama/settings', json={'api_key': KEY}).status_code == 422
    assert client.post(URL + '/unknown/settings', json={}).status_code == 422
    assert client.post(URL + '/ollama/unknown', json={}).status_code == 422
    assert client.post(URL + '/ollama/settings', json={}, headers={'origin':'https://external.invalid'}).status_code == 403
    assert client.post(URL + '/ollama/settings', json={}, headers={'X-AI-Video-Studio': ''}).status_code == 403
    assert check(client, 'ollama', 'simple_generation')['safe_error_category'] == 'settings_required'
    assert not calls


def test_slow_test_keeps_local_health_responsive_and_rejects_duplicate(diagnostic):
    client, _, _ = diagnostic
    check(client, 'ollama', 'settings')
    entered, release = Event(), Event()
    def wait(request):
        entered.set(); assert release.wait(5)
        return httpx.Response(200, json={'response':'TEST_OK','done':True})
    install_transport(client, httpx.MockTransport(wait))
    try:
        assert client.post(URL + '/ollama/simple_generation', json={}).status_code == 202
        assert entered.wait(5)
        assert client.get('/api/health').status_code == 200
        assert client.post(URL + '/ollama/json', json={}).status_code == 409
        assert next(x for x in client.get(URL).json()['providers'] if x['provider']=='ollama')['simple_generation_status'] == 'Test ediliyor'
    finally: release.set()
    client.app.state.ai_diagnostics.futures['ollama'].result(timeout=5)


@pytest.mark.parametrize('test', TESTS)
def test_unexpected_errors_hide_keys_headers_bodies_and_scripts(diagnostic, monkeypatch, test, caplog):
    client, _, _ = diagnostic
    check(client, 'openai', 'settings')
    def fail(*args): raise RuntimeError(KEY + OTHER_KEY + ' Authorization Bearer raw body ' + NARRATION)
    if test == 'settings': monkeypatch.setattr(client.app.state.settings.store, 'write', fail)
    else: client.app.state.ai_diagnostics.provider_factory = fail
    caplog.set_level('INFO')
    view = check(client, 'openai', test)
    assert view['safe_error_category'] == 'unexpected_backend'
    combined = json.dumps(view) + caplog.text
    for private in (KEY, OTHER_KEY, 'Authorization', 'raw body', NARRATION, 'Traceback'): assert private not in combined


@pytest.mark.parametrize('text', ['{"status":"ok"}', '```json\n{"status":"ok"}\n```', 'Here is the result: {"status":"ok"} Thank you.', 'Result:\n```JSON\n{"status":"ok"}\n```\nDone.'])
def test_json_normalization_accepts_only_complete_object_with_harmless_wrappers(text):
    assert parse_json_object(text) == {'status':'ok'}


@pytest.mark.parametrize('text', ['{"status":', '{"broken": {"status":"ok"}', '[{"status":"ok"}]', '{"status":"ok"} {"status":"wrong"}', '{"status":"wrong","status":"ok"}', '{"value":NaN}', '```python\n{"status":"ok"}\n```', '<think>private</think>{"status":"ok"}', 'not JSON'])
def test_json_normalization_never_repairs_or_picks_nested_or_ambiguous_object(text):
    with pytest.raises(ScriptProviderError) as error: parse_json_object(text)
    assert error.value.category == 'invalid_json'


def test_schema_required_fields_are_not_invented():
    class Missing:
        def generate_script(self, prompt): return 'Here is the JSON: {"content_type":"Test"}'
    with pytest.raises(ScriptError) as error:
        YouTubeScriptEngine(Missing(), SecretGuard([])).structured('concept', {}, 'JSON', ConceptBlueprint)
    assert error.value.category == 'schema_invalid'


@pytest.mark.parametrize('response,expected', [({'done':True,'response':'TEST_OK','thinking':'private reasoning'}, 'TEST_OK'), ({'done':True,'response':'{"status":"ok"}'}, '{"status":"ok"}')])
def test_qwen_native_final_response_only_and_official_think_option(response, expected):
    def respond(request):
        assert request.url.path == '/api/generate'
        body = json.loads(request.content)
        assert body['think'] is False and body['stream'] is False and body['model'] == OLLAMA_MODEL
        return httpx.Response(200, json=response)
    provider = OllamaScriptProvider('http://127.0.0.1:11434', OLLAMA_MODEL, transport=httpx.MockTransport(respond))
    assert provider.generate_script('Tiny test') == expected


@pytest.mark.parametrize('body,category', [({'done':True,'response':''},'empty_response'), ({'done':True,'response':'','thinking':'private'},'thinking_unsupported'), ({'done':True,'response':'<think>private</think>TEST_OK'},'thinking_unsupported'), ({'done':False,'response':'partial'},'incomplete_response'), ({'done':True,'message':{'content':'wrong channel'}},'invalid_response')])
def test_qwen_incomplete_empty_and_reasoning_never_enter_script(body, category):
    provider = OllamaScriptProvider('http://localhost:11434', OLLAMA_MODEL, transport=httpx.MockTransport(lambda request:httpx.Response(200,json=body)))
    with pytest.raises(ScriptProviderError) as error: provider.generate_script('Tiny test')
    assert error.value.category == category and 'private' not in str(error.value)


@pytest.mark.parametrize('body,status', [({'error':'this model does not support think=false'},400), ({'done':True,'thinking':'private reasoning','response':'TEST_OK'},200), ({'done':True,'thinking':'private reasoning','response':'wrong final answer'},200)])
def test_unsupported_thinking_option_visible_as_model_compatibility(diagnostic, body, status):
    client, _, _ = diagnostic
    check(client, 'ollama', 'settings')
    install_transport(client,httpx.MockTransport(lambda request:httpx.Response(status,json=body)))
    view = check(client,'ollama','simple_generation')
    assert view['simple_generation_status'] == 'Model uyumsuz' and view['safe_message'] == MESSAGES['thinking_unsupported']
    assert 'private reasoning' not in json.dumps(view)
