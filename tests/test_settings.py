import os
from pathlib import Path
import stat
import subprocess
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.secret_store import SettingsStore, SettingsStorageError
from app.settings import SettingsService, mask_secret
from app.provider_checks import check_ollama

HEADERS = {"X-AI-Video-Studio": "settings"}
# Synthetic fixtures only; no real provider credentials belong in tests.
SECRET = "test-only-credential-1234"


@pytest.fixture
def settings_client(tmp_path):
    with TestClient(create_app(tmp_path / "data"), headers=HEADERS) as client:
        yield client


def test_no_keys_required_and_no_vault_created(settings_client, tmp_path):
    assert settings_client.get('/api/health').status_code == 200
    response = settings_client.get('/api/settings')
    assert response.headers['cache-control'] == 'no-store'
    data = response.json()
    for section in ('ollama', 'openai', 'pexels', 'pixabay', 'ai33'):
        assert data[section]['status'] == 'Yapılandırılmadı'
        assert not data[section]['has_api_key']
    assert data['ollama']['base_url'] == 'http://127.0.0.1:11434'
    assert not data['openai']['enabled']
    assert data['youtube']['status'] == 'Daha sonra'
    assert not (tmp_path / 'data/secrets').exists()


@pytest.mark.parametrize('section', ['openai', 'pexels', 'pixabay', 'ai33'])
def test_save_keys_never_returns_secret(settings_client, section, tmp_path):
    response = settings_client.put(f'/api/settings/{section}', json={'api_key': SECRET})
    assert response.status_code == 200
    assert SECRET not in response.text
    config = response.json()[section]
    assert 'api_key' not in config
    assert config['has_api_key'] is True
    assert config['masked_api_key'] == '••••••••••1234'
    safe = settings_client.get('/api/settings')
    assert SECRET not in safe.text
    assert SECRET not in settings_client.get('/api/diagnostics').text
    vault = tmp_path / 'data/secrets/settings.enc'
    assert vault.exists()
    assert SECRET.encode() not in vault.read_bytes()
    assert SECRET.encode() not in (tmp_path / 'data/app.db').read_bytes()


def test_general_and_optional_provider_fields(settings_client):
    assert settings_client.put('/api/settings/general', json={'content_language': 'tr'}).json()['general']['content_language'] == 'tr'
    data = settings_client.put('/api/settings/openai', json={'enabled': True, 'model': 'user-model', 'api_key': SECRET}).json()
    assert data['openai']['enabled'] is True
    assert data['openai']['status'] == 'Hazır'
    assert data['openai']['connection_test_available'] is True
    # Historical AI33 fields survive the additive Part 7 settings defaults.
    settings_client.app.state.settings.store.write({'ai33':{'base_url':'https://example.com','voice_id':'supplied-voice','model':'supplied-model','api_key':SECRET}})
    data=settings_client.get('/api/settings').json()
    assert data['ai33']['voice_id']=='supplied-voice'
    assert data['ai33']['base_url']=='https://example.com' and data['ai33']['model']=='supplied-model'
    assert data['ai33']['connection_test_available'] is True
    assert data['ai33']['masked_api_key']=='••••••••••1234'



def test_blank_or_omitted_key_preserves_existing(settings_client):
    settings_client.put('/api/settings/openai', json={'api_key': SECRET, 'enabled': True})
    for payload in ({'model': 'another-model'}, {'api_key': ''}, {'api_key': None}):
        response = settings_client.put('/api/settings/openai', json=payload)
        assert response.json()['openai']['masked_api_key'].endswith('1234')
        assert SECRET not in response.text
    assert settings_client.get('/api/settings').json()['openai']['model'] == 'another-model'


def test_clear_removes_key_and_resets_only_selected_section(settings_client, tmp_path):
    settings_client.put('/api/settings/pexels', json={'api_key': SECRET})
    settings_client.put('/api/settings/pixabay', json={'api_key': 'different-dummy-5678'})
    response = settings_client.delete('/api/settings/pexels')
    assert response.status_code == 200
    assert not response.json()['pexels']['has_api_key']
    assert response.json()['pixabay']['has_api_key']
    values = SettingsStore(tmp_path / 'data/secrets').read()
    assert 'api_key' not in values.get('pexels', {})
    assert SECRET not in str(values)


def test_persistence_after_application_restart(tmp_path):
    storage = tmp_path / 'data'
    with TestClient(create_app(storage), headers=HEADERS) as client:
        client.put('/api/settings/pexels', json={'api_key': SECRET})
        client.put('/api/settings/ollama', json={'model': 'local-model:latest'})
    with TestClient(create_app(storage), headers=HEADERS) as client:
        data = client.get('/api/settings').json()
        assert data['pexels']['masked_api_key'] == '••••••••••1234'
        assert data['ollama']['model'] == 'local-model:latest'
        assert client.get('/api/health').status_code == 200
    assert SettingsStore(storage / 'secrets').read()['pexels']['api_key'] == SECRET


@pytest.mark.parametrize('section,payload', [
    ('general', {'content_language': 'invalid'}),
    ('openai', {'enabled': 'yes'}),
    ('openai', {'api_key': 12345}),
    ('openai', {'api_key': 'short'}),
    ('pexels', {'api_key': SECRET + '\n'}),
    ('pixabay', {'api_key': '••••••••••1234'}),
    ('ai33', {'base_url': 'not-a-url', 'api_key': SECRET}),
    ('ai33', {'base_url': 'https://user:password@example.com', 'api_key': SECRET}),
    ('ai33', {'base_url': 'https://example.com?key=' + SECRET}),
    ('ai33', {'base_url': 'https://example.com:99999'}),
    ('ollama', {'base_url': 'http://external.example.com'}),
    ('ollama', {'base_url': 'http://localhost:11434/api/tags'}),
    ('ollama', {'base_url': ''}),
    ('ollama', {'model': 'model with spaces'}),
    ('pexels', {'unexpected_field': SECRET}),
    ('youtube', {'api_key': SECRET}),
])
def test_invalid_input_is_safe_and_does_not_persist(settings_client, section, payload, tmp_path):
    response = settings_client.put(f'/api/settings/{section}', json=payload)
    assert response.status_code == 422
    assert response.json()['message']
    assert SECRET not in response.text
    assert 'input' not in response.json()
    assert not (tmp_path / 'data/secrets/settings.enc').exists()


def test_invalid_json_and_body_shape_do_not_echo_secret(settings_client):
    for content in ('{"api_key":"' + SECRET, '["' + SECRET + '"]'):
        response = settings_client.put('/api/settings/openai', content=content, headers={'Content-Type': 'application/json'})
        assert response.status_code == 422
        assert SECRET not in response.text


def test_invalid_update_keeps_previous_key(settings_client):
    settings_client.put('/api/settings/pexels', json={'api_key': SECRET})
    assert settings_client.put('/api/settings/pexels', json={'api_key': 'bad'}).status_code == 422
    assert settings_client.get('/api/settings').json()['pexels']['has_api_key']


@pytest.mark.parametrize('value,expected', [('', ''), ('tiny', '••••••••••'), (SECRET, '••••••••••1234')])
def test_masking(value, expected):
    assert mask_secret(value) == expected
    if value:
        assert value not in mask_secret(value)


@pytest.mark.parametrize('path', ['/fake/ffmpeg', None])
def test_ffmpeg_detection(settings_client, monkeypatch, path):
    monkeypatch.setattr('app.settings.shutil.which', lambda name: path)
    data = settings_client.get('/api/settings').json()['ffmpeg']
    assert data['found'] == bool(path)
    assert data['executable_path'] == (path or '')
    assert 'Bulundu' in data['message'] if path else 'Bulunamadı' in data['message']
    assert settings_client.get('/settings').status_code == 200


def test_ffmpeg_test_success_and_failure(settings_client, monkeypatch):
    import types
    monkeypatch.setattr('app.settings.shutil.which', lambda name: '/fake/ffmpeg')
    def run(args, **kwargs):
        assert args == ['/fake/ffmpeg', '-version']
        assert kwargs['timeout'] == 5
        return types.SimpleNamespace(returncode=0)
    monkeypatch.setattr('app.main.subprocess.run', run)
    assert settings_client.post('/api/settings/ffmpeg/test').json()['result']['status'] == 'Hazır'
    monkeypatch.setattr('app.settings.shutil.which', lambda name: None)
    assert settings_client.post('/api/settings/ffmpeg/test').json()['result']['status'] == 'Hata'


@pytest.mark.parametrize('section', ['ai33'])
def test_ai33_missing_key_never_makes_network_calls(settings_client, monkeypatch, section):
    def forbidden(*args, **kwargs):
        raise AssertionError('No provider network calls allowed')
    monkeypatch.setattr('app.main.check_ollama', forbidden)
    monkeypatch.setattr('app.provider_checks.httpx.Client', forbidden)
    response = settings_client.post(f'/api/settings/{section}/test')
    assert response.status_code == 200
    assert response.json()['result']['status']=='Hata'
    assert response.json()['result']['category']=='missing_key'


@pytest.mark.parametrize('method', ['PUT', 'DELETE', 'POST'])
def test_cross_origin_mutations_are_blocked(settings_client, method):
    url = '/api/settings/pexels' + ('/test' if method == 'POST' else '')
    response = settings_client.request(method, url, headers={'Origin': 'https://attacker.example'}, json={'api_key': SECRET} if method == 'PUT' else None)
    assert response.status_code == 403
    assert not settings_client.get('/api/settings').json()['pexels']['has_api_key']


def test_mutation_without_custom_header_is_blocked(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.put('/api/settings/pexels', json={'api_key': SECRET}).status_code == 403
        assert client.get('/api/settings', headers={'Origin': 'null'}).status_code == 403
        assert client.get('/api/settings', headers={'Host': 'attacker.example'}).status_code == 400


def test_same_origin_is_allowed(settings_client):
    assert settings_client.put('/api/settings/pexels', json={'api_key': SECRET}, headers={'Origin': 'http://testserver'}).status_code == 200


def test_corrupt_vault_and_missing_key_preserve_files(tmp_path):
    store = SettingsStore(tmp_path / 'secrets')
    store.write({'pexels': {'api_key': SECRET}})
    encrypted = store.vault_path.read_bytes()
    store.key_path.unlink()
    with pytest.raises(SettingsStorageError):
        store.read()
    with pytest.raises(SettingsStorageError):
        store.write({'new': 'value'})
    assert store.vault_path.read_bytes() == encrypted


def test_corrupt_vault_produces_safe_error_and_app_still_runs(tmp_path):
    storage = tmp_path / 'data'
    store = SettingsStore(storage / 'secrets')
    store.write({'pexels': {'api_key': SECRET}})
    store.vault_path.write_bytes(b'damaged')
    with TestClient(create_app(storage), headers=HEADERS) as client:
        assert client.get('/api/health').status_code == 200
        response = client.get('/api/settings')
        assert response.status_code == 503
        assert SECRET not in response.text
        assert client.put('/api/settings/pexels', json={'api_key': 'new-dummy-1234'}).status_code == 503
    assert store.vault_path.read_bytes() == b'damaged'


def test_write_failure_is_safe_and_preserves_current_vault(tmp_path, monkeypatch):
    store = SettingsStore(tmp_path / 'secrets')
    store.write({'pexels': {'api_key': SECRET}})
    previous = store.vault_path.read_bytes()
    def fail(*args):
        raise OSError(SECRET)
    monkeypatch.setattr('app.secret_store.atomic_write', fail)
    with pytest.raises(SettingsStorageError) as error:
        store.write({'new': 'value'})
    assert SECRET not in str(error.value)
    assert store.vault_path.read_bytes() == previous


def test_concurrent_section_updates_are_not_lost(tmp_path):
    service = SettingsService(SettingsStore(tmp_path / 'secrets'))
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(lambda name: service.save(name, {'api_key': SECRET}), ['pexels', 'pixabay', 'ai33']))
    view = service.safe_view()
    assert all(view[name]['has_api_key'] for name in ('pexels', 'pixabay', 'ai33'))


def test_ollama_test_records_status_and_save_resets_it(settings_client, monkeypatch):
    settings_client.put('/api/settings/ollama', json={'model': 'local-model'})
    monkeypatch.setattr('app.main.check_ollama', lambda config: {'status': 'Hata', 'message': 'Ollama uygulamasını açın.'})
    response = settings_client.post('/api/settings/ollama/test')
    assert response.json()['settings']['ollama']['status'] == 'Hata'
    assert settings_client.get('/api/settings').json()['ollama']['status'] == 'Hata'
    assert settings_client.put('/api/settings/ollama', json={'model': 'another-model'}).json()['ollama']['status'] == 'Hazır'


@pytest.mark.parametrize('outcome', ['success', 'missing', 'timeout', 'redirect', 'malformed', 'unauthorized'])
def test_documented_ollama_check_uses_only_tags(monkeypatch, outcome):
    original = httpx.Client
    def respond(request):
        assert str(request.url) == 'http://127.0.0.1:11434/api/tags'
        if outcome == 'timeout':
            raise httpx.ConnectTimeout('internal detail must not reach browser')
        if outcome == 'redirect':
            return httpx.Response(302, headers={'Location': 'http://external.example.com'})
        if outcome == 'unauthorized':
            return httpx.Response(401, text=SECRET)
        if outcome == 'malformed':
            return httpx.Response(200, json={'models': [SECRET]})
        return httpx.Response(200, json={'models': [{'name': 'local-model' if outcome == 'success' else 'other'}]})
    def make_client(**kwargs):
        assert kwargs['trust_env'] is False
        assert kwargs['follow_redirects'] is False
        return original(transport=httpx.MockTransport(respond), **kwargs)
    monkeypatch.setattr('app.provider_checks.httpx.Client', make_client)
    response = check_ollama({'base_url': 'http://127.0.0.1:11434', 'model': 'local-model'})
    assert response['status'] == ('Hazır' if outcome == 'success' else 'Hata')
    assert SECRET not in str(response)
    assert 'internal detail' not in str(response)


def test_settings_files_ignored_by_git(tmp_path):
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run(['git', 'check-ignore', 'data/secrets/vault.key', 'data/secrets/settings.enc', 'data/secrets/.settings-temp'], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0
    assert len(result.stdout.splitlines()) == 3


@pytest.mark.skipif(os.name == 'nt', reason='POSIX permissions; Windows uses DPAPI')
def test_local_permissions_and_key_envelope(tmp_path):
    store = SettingsStore(tmp_path / 'secrets')
    store.write({'pexels': {'api_key': SECRET}})
    assert stat.S_IMODE(store.directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.vault_path.stat().st_mode) == 0o600
    assert store.key_path.read_bytes().startswith(b'LOCAL1:')


@pytest.mark.skipif(os.name != 'nt', reason='Actual DPAPI requires Windows')
def test_windows_dpapi_key_roundtrip(tmp_path):
    store = SettingsStore(tmp_path / 'secrets')
    store.write({'pexels': {'api_key': SECRET}})
    assert store.key_path.read_bytes().startswith(b'DPAPI1:')
    assert store.read()['pexels']['api_key'] == SECRET


def test_windows_key_wrapper_does_not_store_plain_key(monkeypatch):
    import types
    import app.secret_store as module
    key = b'synthetic-fernet-key'
    calls = []
    def dpapi(value, decrypt=False):
        calls.append((value, decrypt))
        return key if decrypt else b'protected-by-windows'
    monkeypatch.setattr(module, 'os', types.SimpleNamespace(name='nt'))
    monkeypatch.setattr(module, '_dpapi', dpapi)
    protected = module.protect_key(key)
    assert protected == b'DPAPI1:protected-by-windows'
    assert key not in protected
    assert module.unprotect_key(protected) == key
    assert calls == [(key, False), (b'protected-by-windows', True)]


def test_non_windows_account_cannot_read_windows_key():
    if os.name == 'nt':
        pytest.skip('Tests unavailable-account behavior on non-Windows')
    from app.secret_store import unprotect_key
    with pytest.raises(SettingsStorageError):
        unprotect_key(b'DPAPI1:account-protected-data')
