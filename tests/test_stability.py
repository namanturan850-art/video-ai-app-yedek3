"""Phase A gate: real vault persistence and simulated Windows/API failures."""
from pathlib import Path
import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.secret_store import SettingsStore, SettingsStorageError, atomic_write
from app.settings import SettingsService
from app.providers.text_api import OpenAIScriptProvider
from app.providers.base import ScriptProviderError
from test_scripts import studio, run, KEY, OTHER_KEY, MODEL


def vault_workflow(directory):
    service = SettingsService(SettingsStore(directory))
    service.save('gemini', {'api_key': KEY})
    service.record_gemini_models(service.gemini_config(), [MODEL])
    service.save('gemini', {'model': MODEL})
    original_key = service.store.key_path.read_bytes()
    service.save('openai', {'api_key': OTHER_KEY, 'enabled': True, 'model': 'verified-user-model'})
    restarted = SettingsService(SettingsStore(directory))
    assert restarted.safe_view()['openai']['enabled'] is True
    assert restarted.script_config('openai')['api_key'] == OTHER_KEY
    restarted.save('openai', {'api_key': 'synthetic-replacement-key-9012'})
    assert SettingsService(SettingsStore(directory)).script_config('openai')['api_key'].endswith('9012')
    restarted.clear('openai')
    assert restarted.gemini_config()['api_key'] == KEY
    assert restarted.safe_view()['gemini']['model_verified']
    assert restarted.store.key_path.read_bytes() == original_key
    assert KEY.encode() not in restarted.store.vault_path.read_bytes()


def test_existing_gemini_add_update_clear_openai_restart(tmp_path):
    vault_workflow(tmp_path / 'secrets')


@pytest.mark.skipif(os.name != 'nt', reason='Real same-user Windows DPAPI requires Windows')
def test_real_windows_existing_vault_workflow(tmp_path):
    vault_workflow(tmp_path / 'secrets')
    assert (tmp_path / 'secrets/vault.key').read_bytes().startswith(b'DPAPI1:')


@pytest.mark.parametrize(('kind', 'category'), [('temporary', 'temp_file_failed'), ('replace', 'atomic_replace_failed'), ('locked', 'storage_locked'), ('decrypt', 'key_decrypt_failed'), ('folder', 'folder_permission'), ('encrypt', 'encryption_failed')])
def test_safe_vault_error_categories_preserve_both_files(tmp_path, monkeypatch, kind, category, caplog):
    store = SettingsStore(tmp_path / 'secrets')
    store.write({'gemini': {'api_key': KEY}})
    before = {path: path.read_bytes() for path in (store.key_path, store.vault_path)}
    def fail(*args, **kwargs):
        error = PermissionError(KEY)
        if kind == 'locked':
            error.winerror = 32
        raise error
    if kind == 'temporary': monkeypatch.setattr('app.secret_store.tempfile.mkstemp', fail)
    elif kind in ('replace', 'locked'): monkeypatch.setattr('app.secret_store.os.replace', fail)
    elif kind == 'decrypt': monkeypatch.setattr('app.secret_store.unprotect_key', fail)
    elif kind == 'folder': monkeypatch.setattr(Path, 'mkdir', fail)
    elif kind == 'encrypt': monkeypatch.setattr('app.secret_store.Fernet.encrypt', lambda *a: (_ for _ in ()).throw(ValueError(KEY)))
    with caplog.at_level('INFO'), pytest.raises(SettingsStorageError) as error:
        store.write({'openai': {'api_key': OTHER_KEY}})
    assert error.value.category == category
    assert KEY not in str(error.value) and KEY not in caplog.text
    assert all(path.read_bytes() == content for path, content in before.items())


def test_transient_windows_lock_retries_with_closed_handle(tmp_path, monkeypatch):
    target = tmp_path / 'settings.enc'
    target.write_bytes(b'old encrypted vault')
    replace, calls = os.replace, []
    def briefly_locked(source, destination):
        calls.append(1)
        if len(calls) < 3:
            error = PermissionError('synthetic lock'); error.winerror = 32; raise error
        replace(source, destination)
    monkeypatch.setattr('app.secret_store.os.replace', briefly_locked)
    atomic_write(target, b'new encrypted vault')
    assert target.read_bytes() == b'new encrypted vault' and len(calls) == 3
    assert not list(tmp_path.glob('.settings-*'))


@pytest.mark.parametrize(('status', 'code', 'category'), [(401, 'invalid_api_key', 'key_rejected'), (403, '', 'key_rejected'), (404, 'model_not_found', 'model_unavailable'), (429, 'insufficient_quota', 'billing_quota'), (429, 'rate_limit_exceeded', 'rate_limit'), (500, '', 'upstream_error'), (400, '', 'invalid_model')])
def test_openai_official_read_only_test_and_safe_failures(status, code, category, caplog):
    def respond(request):
        assert request.method == 'GET'
        assert str(request.url) == 'https://api.openai.com/v1/models/user-model'
        assert request.headers['Authorization'] == 'Bearer ' + OTHER_KEY
        return httpx.Response(status, json={'error': {'code': code, 'message': OTHER_KEY}}, headers={'Retry-After': '45'})
    provider = OpenAIScriptProvider(OTHER_KEY, 'user-model', transport=httpx.MockTransport(respond))
    with caplog.at_level('INFO'), pytest.raises(ScriptProviderError) as error:
        provider.test_connection()
    assert error.value.category == category
    assert OTHER_KEY not in str(error.value) and OTHER_KEY not in caplog.text
    assert category in caplog.text


def test_openai_test_success_enable_disable_missing_key(studio, monkeypatch):
    client, _, _, _ = studio
    provider = OpenAIScriptProvider(OTHER_KEY, 'openai-test-model', transport=httpx.MockTransport(lambda req: httpx.Response(200, json={'id': 'openai-test-model'})))
    monkeypatch.setattr('app.main.make_script_provider', lambda *a, **k: provider)
    assert client.post('/api/settings/openai/test', headers={'X-AI-Video-Studio': 'settings'}).json()['result']['status'] == 'Hazır'
    monkeypatch.undo()
    client.app.state.settings.save('openai', {'enabled': False})
    response = client.post('/api/settings/openai/test', headers={'X-AI-Video-Studio': 'settings'})
    assert response.json()['result']['category'] == 'provider_disabled'
    client.app.state.settings.clear('openai')
    client.app.state.settings.save('openai', {'enabled': True})
    assert client.post('/api/settings/openai/test', headers={'X-AI-Video-Studio': 'settings'}).json()['result']['category'] == 'missing_key'
    # Historical incorrect paste must not send another provider's key in a model URL.
    store = client.app.state.settings.store
    values = store.read(); values['openai'].update(api_key=OTHER_KEY, model=KEY)
    store.write(values)
    response = client.post('/api/settings/openai/test', headers={'X-AI-Video-Studio': 'settings'})
    assert response.json()['result']['category'] == 'invalid_settings'
    assert KEY not in response.text and OTHER_KEY not in response.text


@pytest.mark.parametrize('error_type', [httpx.ReadTimeout, httpx.ConnectError])
def test_openai_timeout_and_internet_failure(error_type):
    def fail(request): raise error_type(OTHER_KEY)
    provider = OpenAIScriptProvider(OTHER_KEY, MODEL, transport=httpx.MockTransport(fail))
    with pytest.raises(ScriptProviderError) as error: provider.test_connection()
    assert error.value.category == ('generation_timeout' if error_type == httpx.ReadTimeout else 'no_internet')
    assert OTHER_KEY not in str(error.value)


def test_retry_after_preserves_sections_and_blocks_rapid_resume(studio):
    client, project, fake, _ = studio
    client.patch(f'/api/projects/{project["id"]}', json={'target_duration_minutes': 10})
    original = fake.generate_script
    def fail_second(prompt):
        if prompt.startswith('TASK: section') and '"index": 2' in prompt:
            raise ScriptProviderError('safe quota message', category='quota_limit', retry_after=30)
        return original(prompt)
    fake.generate_script = fail_second
    view = run(studio)
    assert view['job']['completed_sections'] == 1
    assert view['job']['progress']['error_category'] == 'quota_limit'
    assert client.post(f'/api/projects/{project["id"]}/script/jobs/{view["job"]["id"]}/resume', json={'confirm_replace_approved': False}).status_code == 429
    assert client.get(f'/api/projects/{project["id"]}/script').json()['job']['partial_text'] == view['job']['partial_text']


def test_unexpected_openai_settings_error_returns_safe_json(studio, monkeypatch):
    client, _, _, _ = studio
    def fail(*a, **k): raise RuntimeError(OTHER_KEY)
    monkeypatch.setattr('app.main.make_script_provider', fail)
    response = client.post('/api/settings/openai/test', headers={'X-AI-Video-Studio': 'settings'})
    assert response.status_code == 500 and OTHER_KEY not in response.text
    assert response.json()['category'] == 'unexpected_backend'
