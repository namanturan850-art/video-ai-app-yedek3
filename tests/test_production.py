import base64
from contextlib import closing
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.database import initialize_database
from app.main import create_app
from app.production import visual_blocks, production_checks
from app.production_settings import ImageSettings
from app.providers.base import ScriptProviderError
from app.providers.images import ImageProvider, LocalGPUImageProvider, GeminiImageProvider, OpenAIImageProvider, image_candidates
from app.scripts.models import ScriptError
from test_scripts import studio, run, KEY, OTHER_KEY, MODEL

SETTINGS_HEADERS = {'X-AI-Video-Studio': 'settings'}
PNG = b'\x89PNG\r\n\x1a\nsynthetic-test-image'


def block(text, composition='wide'):
    return {'narration': text, 'purpose': 'Konuyu göster', 'mood': 'technology', 'visual_intent': 'Elektrikli otomobil bağlamı',
        'stock_query': 'electric cars Germany dealership', 'alternative_stock_queries': ['EV charging station Europe', 'modern electric vehicle showroom'],
        'media_type': 'stock_video', 'overlay_text': 'Elektrikli otomobiller', 'transition': 'hard_cut', 'motion': 'none', 'composition': composition, 'importance': 80}


def scene(unit_ids, composition='wide'):
    metadata=block('',composition);metadata.pop('narration')
    return {'unit_ids':unit_ids,**metadata}


@pytest.fixture
def production_studio(studio):
    client, project, fake, _ = studio
    current = run(studio)['current']
    base = f'/api/projects/{project["id"]}/script'
    client.post(base + f'/versions/{current["id"]}/approve', json={'confirm': True})
    original = fake.generate_script
    def visual(prompt):
        if prompt.startswith('TASK: visual'):
            payload = json.loads(prompt.split('INPUT DATA (not instructions):\n')[1])
            fake.calls.append(('visual', payload, prompt))
            ids=[unit['unit_id'] for unit in payload['narration_units']]
            half=max(1,len(ids)//2)
            groups=payload.get('metadata_repair',{}).get('required_unit_groups') or [ids[:half]]+([ids[half:]] if ids[half:] else [])
            return json.dumps({'scenes':[scene(group,'wide' if index==0 else 'close') for index,group in enumerate(groups)]})
        return original(prompt)
    fake.generate_script = visual
    response = client.post(f'/api/projects/{project["id"]}/production/plan', json={'provider': 'gemini', 'cost_confirmed': True, 'confirm_replace_plan': False})
    assert response.status_code == 202
    client.app.state.scripts.futures[response.json()['job_id']].result(timeout=5)
    view = client.get(f'/api/projects/{project["id"]}/production').json()
    assert view['plan'], client.get(base).json()['job']
    return studio


def test_approved_visual_plan_queries_language_timing_and_persistence(production_studio):
    client, project, _, data = production_studio
    route = f'/api/projects/{project["id"]}/production'
    view = client.get(route).json()
    assert view['media_priority'] == ['pexels', 'pixabay', 'local', 'cloud_with_permission']
    assert not view['render_available'] and not view['upload_available']
    assert all(block['language'] == 'de' and block['stock_query_language'] == 'en' and block['timing_source'] == 'estimated' for block in view['plan']['blocks'])
    assert view['plan']['blocks'][-1]['end'] == 120
    assert 'medya' in ' '.join(view['warnings']).lower()
    assert KEY not in json.dumps(view)
    assert (data / 'projects' / project['id'] / 'script/visual_plan.json').exists()
    with TestClient(create_app(data)) as restarted: assert restarted.get(route).json() == view


def test_visual_plan_requires_current_approval_and_cost_consent(studio):
    client, project, fake, _ = studio
    current = run(studio)['current']
    route = f'/api/projects/{project["id"]}/production/plan'
    payload = {'provider': 'gemini', 'cost_confirmed': True, 'confirm_replace_plan': False}
    assert client.post(route, json=payload).status_code == 409
    client.post(f'/api/projects/{project["id"]}/script/versions/{current["id"]}/approve', json={'confirm': True})
    assert client.post(route, json={**payload, 'cost_confirmed': False}).status_code == 409
    assert all(task != 'visual' for task, _, _ in fake.calls)


def test_media_deduplication_missing_file_and_resolution_checks(production_studio):
    client, project, _, _ = production_studio
    route = f'/api/projects/{project["id"]}/production'
    blocks = client.get(route).json()['plan']['blocks']
    media = {'provider': 'pexels', 'media_id': 'synthetic-clip-id', 'width': 1280, 'height': 720}
    assert client.put(route + f'/blocks/{blocks[0]["id"]}/media', json=media).status_code == 200
    assert client.put(route + f'/blocks/{blocks[1]["id"]}/media', json=media).status_code == 409
    result = client.get(route).json()
    assert not result['plan']['blocks'][0]['media']['available']
    assert 'çözünürlük' in ' '.join(result['warnings']) and 'dosyası henüz doğrulanmadı' in ' '.join(result['warnings'])


def test_actual_narration_timing_aligns_blocks_and_rejects_wrong_text(production_studio):
    client, project, _, _ = production_studio
    route = f'/api/projects/{project["id"]}/production'
    plan = client.get(route).json()['plan']
    timings = [{'text': block['narration'], 'start': float(index*45), 'end': float((index+1)*45)} for index, block in enumerate(plan['blocks'])]
    assert client.put(route + '/timing', json={'timings': timings}).status_code == 200
    assert client.get(route).json()['plan']['timing_source'] == 'tts'
    timings[0]['text'] = 'unrelated text'
    assert client.put(route + '/timing', json={'timings': timings}).status_code == 422


def test_music_preferences_and_pre_render_checks_are_truthful(production_studio):
    client, project, _, _ = production_studio
    route = f'/api/projects/{project["id"]}/production'
    payload = {'enabled': True, 'mood': 'documentary', 'local_file_label': 'my-licensed-track.mp3', 'license_confirmed': True, 'volume': .8, 'fade_in': 2., 'fade_out': 4., 'ducking': True, 'section_changes': ['major-section-2']}
    response = client.put(route, json={'music': payload})
    assert response.status_code == 200
    assert response.json()['plan']['music'] == payload
    assert 'bastırabilir' in ' '.join(response.json()['warnings'])
    assert not response.json()['render_available']
    assert client.put(route, json={'music': {**payload, 'volume': 3.}}).status_code == 422
    assert client.put(route, json={'music': {**payload, 'local_file_label': KEY}}).status_code == 422


def test_visual_input_coverage_semantic_queries_and_diversity():
    with pytest.raises(ScriptError): visual_blocks({'scenes':[scene(['unknown'])]}, 'actual script', 'es', 135)
    bad = scene(['U1']); bad['stock_query'] = 'car'
    with pytest.raises(ScriptError): visual_blocks({'scenes':[bad]}, 'actual script', 'es', 135)
    blocks = visual_blocks({'scenes':[scene([f'U{i+1}']) for i in range(4)]}, 'Sentence one. Sentence two. Sentence three. Sentence four.', 'es', 135)
    for item in blocks: item['media_type'] = 'stock_image'
    plan = {'version_id': 'version', 'blocks': blocks, 'language': 'es', 'width': 1920, 'height': 1080, 'music': {'enabled': False, 'local_file_label': '', 'license_confirmed': False, 'volume': .15}}
    warnings = production_checks(plan, {'id': 'version', 'status': 'approved'}, {'subtitles_enabled': False})
    assert any('kompozisyon' in x for x in warnings) and any('sabit görsel' in x for x in warnings)
    assert all(item['overlay_language'] == 'es' for item in blocks)


def test_image_settings_defaults_encrypted_reuse_clear_and_restart(studio):
    client, _, _, data = studio
    view = client.get('/api/settings').json()
    assert view['images']['paid_usage'] == 'off'
    assert image_candidates(client.app.state.settings.image_config()) == []
    payload = {'engine': 'local', 'local_enabled': True, 'local_model': 'installed-licensed-model', 'workflow': 'user-workflow', 'license_confirmed': True, 'width': 1280, 'height': 720}
    response = client.put('/api/settings/images', json=payload, headers=SETTINGS_HEADERS)
    assert response.status_code == 200, response.text
    assert KEY not in response.text and OTHER_KEY not in response.text
    with TestClient(create_app(data)) as restarted: assert restarted.get('/api/settings').json()['images']['workflow'] == 'user-workflow'
    client.delete('/api/settings/images', headers=SETTINGS_HEADERS)
    assert client.app.state.settings.gemini_config()['api_key'] == KEY
    assert client.app.state.settings.script_config('openai')['api_key'] == OTHER_KEY


@pytest.mark.parametrize('payload', [{'local_url': 'https://external.example'}, {'width': 1024, 'height': 1024}, {'engine': 'unknown'}, {'paid_usage': 'yes'}, {'api_key': KEY}, {'openai_model': OTHER_KEY}, {'gemini_model': 'placeholder'}])
def test_invalid_image_config_never_leaks_or_changes_existing(studio, payload):
    client, _, _, _ = studio
    before = client.app.state.settings.image_config()
    response = client.put('/api/settings/images', json=payload, headers=SETTINGS_HEADERS)
    assert response.status_code == 422
    assert KEY not in response.text and OTHER_KEY not in response.text
    assert client.app.state.settings.image_config() == before


def test_image_selection_free_first_never_paid_without_permission():
    config = ImageSettings(local_enabled=True, local_model='installed', workflow='user-workflow', license_confirmed=True, gemini_model='user-selected-model', openai_model='user-selected-image-model').model_dump()
    assert image_candidates(config, stock_found=True) == ['stock']
    assert image_candidates(config) == ['local']
    assert image_candidates({**config, 'paid_usage': 'ask'}) == ['local']
    assert image_candidates({**config, 'paid_usage': 'ask'}, cost_confirmed=True) == ['local', 'gemini', 'openai']
    assert image_candidates({**config, 'engine': 'off'}) == []
    assert image_candidates({**config, 'engine': 'openai', 'paid_usage': 'ask'}, cost_confirmed=True) == ['openai']
    assert image_candidates({**config, 'license_confirmed': False}) == []


def test_local_gpu_official_api_test_models_and_prepared_execution():
    def respond(request):
        assert request.url.host == '127.0.0.1'
        if request.url.path == '/system_stats': return httpx.Response(200, json={'devices': [{'type': 'cuda', 'name': 'NVIDIA synthetic RTX 5070'}]})
        assert request.url.path == '/object_info/CheckpointLoaderSimple'
        return httpx.Response(200, json={'CheckpointLoaderSimple': {'input': {'required': {'ckpt_name': [['installed-model']]}}}})
    provider = LocalGPUImageProvider({'local_enabled': True}, transport=httpx.MockTransport(respond))
    assert isinstance(provider, ImageProvider)
    assert 'CUDA' in provider.test_connection()['message']
    assert provider.models() == ['installed-model']
    with pytest.raises(ScriptProviderError) as error: provider.generate_image('prompt')
    assert error.value.category == 'prepared_only'


@pytest.mark.parametrize('provider_type', ['gemini', 'openai'])
def test_official_cloud_image_contract_cost_gate_and_no_key_in_body(provider_type):
    def respond(request):
        body = json.loads(request.content)
        assert KEY not in json.dumps(body) and KEY not in str(request.url)
        if provider_type == 'gemini':
            assert request.headers['x-goog-api-key'] == KEY
            assert request.url.path == '/v1beta/models/test-image-model:generateContent'
            assert body['generationConfig']['responseModalities'] == ['TEXT', 'IMAGE']
            return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'inlineData': {'mimeType': 'image/png', 'data': base64.b64encode(PNG).decode()}}]}}]})
        assert request.url == 'https://api.openai.com/v1/images/generations'
        assert request.headers['Authorization'] == 'Bearer ' + KEY and body['n'] == 1
        return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(PNG).decode()}]})
    transport = httpx.MockTransport(respond)
    provider = GeminiImageProvider(KEY, 'test-image-model', transport=transport) if provider_type == 'gemini' else OpenAIImageProvider(KEY, 'test-image-model', transport=transport)
    assert isinstance(provider, ImageProvider)
    with pytest.raises(ScriptProviderError): provider.generate_image('prompt')
    assert provider.generate_image('prompt', cost_confirmed=True)['data'] == PNG


def test_schema4_upgrade_preserves_scripts_projects_and_credentials(studio):
    client, project, _, data = studio
    current = run(studio)['current']
    vault = (data / 'secrets/settings.enc').read_bytes()
    with closing(client.app.state.projects._connection()) as db, db:
        db.execute('DROP TABLE script_artifacts'); db.execute('DROP TABLE project_production')
        db.execute("UPDATE app_metadata SET value='4' WHERE key='schema_version'")
    initialize_database(data)
    assert client.get(f'/api/projects/{project["id"]}/script').json()['current'] == current
    assert (data / 'secrets/settings.enc').read_bytes() == vault


def test_gemini_image_discovery_uses_saved_key_and_never_assumes_image_capability(studio, monkeypatch):
    client, _, _, _ = studio
    def respond(request):
        assert request.method == 'GET' and request.headers['x-goog-api-key'] == KEY
        return httpx.Response(200, json={'models': [{'name': 'models/user-image-capable-model', 'supportedGenerationMethods': ['generateContent']}]})
    original = GeminiImageProvider
    monkeypatch.setattr('app.main.GeminiImageProvider', lambda key, model: original(key, model, transport=httpx.MockTransport(respond)))
    response = client.post('/api/settings/images/gemini/models', headers=SETTINGS_HEADERS)
    assert response.status_code == 200 and KEY not in response.text
    assert response.json()['images']['gemini_models'] == ['user-image-capable-model']
    assert client.put('/api/settings/images', json={'gemini_model': 'user-image-capable-model'}, headers=SETTINGS_HEADERS).status_code == 200
    outcome = client.post('/api/settings/images/gemini/test', headers=SETTINGS_HEADERS)
    assert outcome.json()['result']['status'] == 'Hazır'
    assert 'garanti etmez' in client.get('/api/settings').json()['images']['message']


def test_openai_image_test_reuses_encrypted_key_without_generation(studio, monkeypatch):
    client, _, _, _ = studio
    client.put('/api/settings/images', json={'openai_model': 'user-image-model'}, headers=SETTINGS_HEADERS)
    def respond(request):
        assert request.method == 'GET' and request.headers['Authorization'] == 'Bearer ' + OTHER_KEY
        return httpx.Response(200, json={'id': 'user-image-model'})
    original = OpenAIImageProvider
    monkeypatch.setattr('app.main.OpenAIImageProvider', lambda key, model: original(key, model, transport=httpx.MockTransport(respond)))
    response = client.post('/api/settings/images/openai/test', headers=SETTINGS_HEADERS)
    assert response.status_code == 200 and OTHER_KEY not in response.text


def test_production_requires_confirmation_before_replacing_existing_plan(production_studio):
    client, project, _, _ = production_studio
    route = f'/api/projects/{project["id"]}/production'
    before = client.get(route).json()['plan']
    payload = {'provider': 'gemini', 'cost_confirmed': True, 'confirm_replace_plan': False}
    assert client.post(route + '/plan', json=payload).status_code == 409
    assert client.get(route).json()['plan'] == before


@pytest.mark.parametrize('provider_type', ['gemini', 'openai'])
def test_cloud_image_failure_bodies_and_keys_stay_private(provider_type):
    transport = httpx.MockTransport(lambda request: httpx.Response(429, json={'error': {'message': KEY}}))
    provider = GeminiImageProvider(KEY, 'test-model', transport=transport) if provider_type == 'gemini' else OpenAIImageProvider(KEY, 'test-model', transport=transport)
    with pytest.raises(ScriptProviderError) as error: provider.generate_image('image prompt', cost_confirmed=True)
    assert error.value.category == 'quota_limit' and KEY not in str(error.value)
