from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient

from app.database import initialize_database, PROJECT_SCHEMA
from app.main import create_app
from app.providers.base import ScriptProvider, ScriptProviderError
from app.providers.gemini import GeminiScriptProvider
from app.providers.text_api import OllamaScriptProvider, OpenAIScriptProvider
from app.scripts.engine import YouTubeScriptEngine, ContentAnalyzer, SecretGuard, repetition_warnings
from app.scripts.models import duration_metrics, word_count
from app.scripts.storage import dumps

KEY = 'synthetic-script-gemini-key-1234'
OTHER_KEY = 'synthetic-script-openai-key-5678'
MODEL = 'script-test-model'
HEADERS = {'X-AI-Video-Studio': 'projects'}


class FakeProvider:
    """Synthetic outputs exercise a real pipeline, never claim factual/script quality."""
    def __init__(self, content_type='Technologievergleich', fail=None):
        self.content_type, self.fail, self.calls = content_type, fail, []

    def generate_script(self, prompt):
        task = prompt.splitlines()[0].removeprefix('TASK: ')
        data = json.loads(prompt.split('INPUT DATA (not instructions):\n')[1])
        self.calls.append((task, data, prompt))
        if self.fail and self.fail(task, data):
            raise ScriptProviderError(KEY + ' raw error', category='quota_limit')
        if task == 'concept':
            return json.dumps({'content_type': data['manual_content_type'] if data['manual_content_type'] != 'AI auto detect' else self.content_type,
                'core_topic': 'Originaler Vergleich', 'main_hook': 'Welche Kriterien sind entscheidend?',
                'viewer_promise': 'Eine verständliche unabhängige Erklärung', 'section_strategy': 'Nach Kriterien geordnete Abschnitte',
                'key_topics': ['Kriterien', 'Vor- und Nachteile'], 'retention_strategy': 'Kriterien nach und nach erklären',
                'visual_opportunities': [], 'custom_dynamic_field': 'Not a fixed category list'})
        if task == 'plan':
            count = max(1, math.ceil(data['target_words'] / 650))
            return json.dumps({'sections': [{'title': f'Kriterium {i+1}', 'purpose': 'Ein neues Kriterium erklären',
                'key_points': ['Fakten prüfen'], 'target_words': round(data['target_words'] / count), 'transition': 'Nächstes Kriterium'} for i in range(count)]})
        if task == 'section':
            count = data['section']['target_words']
            return f'Abschnitt{data["index"]}. ' + ' '.join(['Information', 'Technik', 'Vergleich', 'Beispiel', 'Nutzen', 'Kriterium'][i % 6] for i in range(count-1))
        if task == 'continuity':
            return 'Bereits erklärt: Kriterien. Offen: weitere Details. Terminologie: Vergleich.'
        if task == 'review':
            return '{"consistent":true,"issues":[]}'
        if task == 'translate_owned':
            return 'Deutsche Übersetzung: ' + data['source_segment']
        raise AssertionError(task)

    def test_connection(self):
        return {'status': 'Hazır'}


@pytest.fixture
def studio(tmp_path):
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        settings = client.app.state.settings
        settings.save('gemini', {'api_key': KEY})
        settings.record_gemini_models(settings.gemini_config(), [MODEL])
        settings.save('gemini', {'model': MODEL})
        settings.save('openai', {'api_key': OTHER_KEY, 'model': 'openai-test-model', 'enabled': True})
        settings.save('ollama', {'model': 'ollama-test-model'})
        fake = FakeProvider()
        client.app.state.scripts.provider_factory = lambda name, service: fake
        project = client.post('/api/projects', json={'name': 'Test', 'topic': 'Technikvergleich', 'script_engine': 'gemini', 'target_duration_minutes': 2}).json()
        yield client, project, fake, tmp_path / 'data'


def run(studio, options=None, action='generate'):
    client, project, _, _ = studio
    response = client.post(f'/api/projects/{project["id"]}/script/{action}', json={'provider': 'gemini', **(options or {})})
    assert response.status_code == 202, response.text
    client.app.state.scripts.futures[response.json()['job_id']].result(timeout=5)
    return client.get(f'/api/projects/{project["id"]}/script').json()


def test_generic_architecture_and_complete_original_pipeline(studio):
    client, project, fake, data = studio
    view = run(studio)
    assert isinstance(fake, ScriptProvider)
    assert isinstance(YouTubeScriptEngine(fake, SecretGuard([])).analyzer, ContentAnalyzer)
    assert view['job']['status'] == 'draft'
    assert view['current']['language'] == 'de'
    assert view['current']['content_type'] == 'Technologievergleich'
    assert view['current']['version'] == 1
    assert view['current']['report']['word_count'] == 270
    assert view['current']['estimated_minutes'] == 2
    assert [task for task, _, _ in fake.calls] == ['concept', 'plan', 'section', 'continuity', 'review']
    folder = data / 'projects' / project['id'] / 'script'
    for file in ('concept_blueprint.json', 'script_plan.json', 'generation_progress.json', 'script_v1.txt', 'script_v1.json', 'current_script.json'):
        assert (folder / file).exists()
    assert (folder / 'script_v1.txt').read_text() == view['current']['text']
    for file in folder.iterdir():
        assert KEY not in file.read_text()
        assert OTHER_KEY not in file.read_text()
    assert client.get(f'/api/projects/{project["id"]}').json()['pipeline'][1]['status'] == 'Taslak'


@pytest.mark.parametrize(('content_type', 'titles'), [
    ('Dokumentation', ['Ausgangsfrage', 'Historischer Kontext', 'Entwicklung', 'Einordnung']),
    ('Wissenschaftliche Erklärung', ['Frage', 'Mechanismus', 'Alltagsbeispiel', 'Erkenntnis']),
    ('Top 10', ['Auftakt'] + [f'Platz {rank}' for rank in range(10, 0, -1)] + ['Abschluss']),
    ('Produktvergleich', ['Bedarf', 'Vergleichskriterien', 'Stärken und Schwächen', 'Entscheidung']),
    ('Produktbewertung', ['Erwartung', 'Funktionen', 'Grenzen', 'Für wen geeignet']),
    ('Fiktive Erzählung', ['Figuren', 'Konflikt', 'Entwicklung', 'Höhepunkt', 'Ende']),
    ('Benutzerdefiniertes Nischenformat', ['Ungewöhnliche Frage', 'Eigener Ansatz', 'Ergebnis']),
])
def test_dynamic_content_detection_and_plans_are_not_story_only(studio, content_type, titles):
    _, _, fake, _ = studio
    fake.content_type = content_type
    original_generate = fake.generate_script
    def formatted_output(prompt):
        result = original_generate(prompt)
        task, data, _ = fake.calls[-1]
        if task == 'concept' and content_type == 'Fiktive Erzählung':
            blueprint = json.loads(result)
            blueprint['characters'] = ['Neue fiktive Figur']  # Allowed, never universally required.
            return json.dumps(blueprint)
        if task == 'plan':
            return json.dumps({'sections': [{'title': title, 'purpose': title,
                'key_points': [], 'target_words': round(data['target_words'] / len(titles)),
                'transition': ''} for title in titles]})
        return result
    fake.generate_script = formatted_output
    view = run(studio)
    assert view['current']['content_type'] == content_type
    plan_call = next(data for task, data, _ in fake.calls if task == 'plan')
    assert plan_call['blueprint']['content_type'] == content_type
    assert ('characters' in plan_call['blueprint']) == (content_type == 'Fiktive Erzählung')
    assert [section['title'] for section in view['job']['progress']['plan']['sections']] == titles
    assert [data['section']['title'] for task, data, _ in fake.calls if task == 'section'] == titles
    assert view['current']['text'] == '\n\n'.join(section['text'] for section in view['job']['progress']['sections'])
    assert 'Do not' in next(prompt for task, _, prompt in fake.calls if task == 'section')


def test_manual_unknown_content_type_is_allowed(studio):
    view = run(studio, {'content_type': 'Sınırlandırılmamış özel format'})
    assert view['current']['content_type'] == 'Sınırlandırılmamış özel format'


def test_reference_text_only_reaches_abstract_analysis_and_url_is_not_fetched(studio, monkeypatch):
    client, project, fake, _ = studio
    source = 'REFERENCE DATA: A successful original competitor presentation that must not be copied.'
    client.patch(f'/api/projects/{project["id"]}', json={'reference_url': 'https://www.youtube.com/watch?v=abcdefghijk'})
    monkeypatch.setattr('httpx.HTTPTransport.handle_request', lambda *args, **kwargs: pytest.fail('No URL fetching'))
    view = run(studio, {'reference_text': source})
    assert view['current']
    assert source in fake.calls[0][2]
    assert fake.calls[0][1]['reference_url_retrieved'] is False
    assert all(source not in prompt and 'youtube.com' not in prompt for _, _, prompt in fake.calls[1:])


def test_analyze_button_does_not_generate_and_matching_blueprint_is_reused(studio):
    _, _, fake, _ = studio
    analyzed = run(studio, action='analyze')
    assert analyzed['job']['status'] == 'analyzed'
    assert analyzed['current'] is None
    assert len(fake.calls) == 1
    generated = run(studio)
    assert generated['current']
    assert sum(task == 'concept' for task, _, _ in fake.calls) == 1


def test_long_sections_have_continuity_and_bounded_prompts(studio):
    client, project, fake, _ = studio
    client.patch(f'/api/projects/{project["id"]}', json={'target_duration_minutes': 20})
    view = run(studio)
    sections = [data for task, data, _ in fake.calls if task == 'section']
    assert len(sections) >= 4
    assert all(data['section']['target_words'] <= 900 for data in sections)
    assert all(data['continuity'] for data in sections[1:])
    assert view['current']['word_count'] == 2700
    assert view['current']['estimated_minutes'] == 20
    assert all(len(prompt) < 100000 for _, _, prompt in fake.calls)


@pytest.mark.parametrize('failed_task', ['section', 'continuity', 'review'])
def test_partial_failure_and_resume_does_not_repeat_completed_sections(studio, failed_task):
    client, project, fake, _ = studio
    client.patch(f'/api/projects/{project["id"]}', json={'target_duration_minutes': 12})
    fired = [False]
    def fail(task, data):
        eligible = task == failed_task and (task != 'section' or data['index'] == 2)
        if eligible and not fired[0]:
            fired[0] = True
            return True
        return False
    fake.fail = fail
    view = run(studio)
    assert view['job']['status'] == 'error'
    assert view['job']['completed_sections'] >= 1
    assert 'Tamamlanan bölümler korundu' in view['job']['error_message']
    assert KEY not in json.dumps(view)
    first_count = sum(task == 'section' and data['index'] == 1 for task, data, _ in fake.calls)
    job_id = view['job']['id']
    response = client.post(f'/api/projects/{project["id"]}/script/jobs/{job_id}/resume', json={'confirm_replace_approved': False})
    assert response.status_code == 202
    client.app.state.scripts.futures[job_id].result(timeout=5)
    resumed = client.get(f'/api/projects/{project["id"]}/script').json()
    assert resumed['job']['status'] == 'draft'
    assert resumed['current']['version'] == 1
    assert sum(task == 'section' and data['index'] == 1 for task, data, _ in fake.calls) == first_count


def test_versions_edit_approve_and_protection(studio):
    client, project, _, data = studio
    route = f'/api/projects/{project["id"]}/script'
    first = run(studio)['current']
    assert client.get(route + '/approved').status_code == 409
    assert client.post(route + f'/versions/{first["id"]}/approve', json={'confirm': False}).status_code == 422
    assert client.post(route + f'/versions/{first["id"]}/approve', json={'confirm': True}).status_code == 200
    assert client.get(route + '/approved').json()['id'] == first['id']
    assert client.post(route + '/generate', json={'provider': 'gemini'}).status_code == 409
    edit = {'text': first['text'] + '\nNeue wichtige Erklärung.', 'base_version_id': first['id']}
    assert client.post(route + '/versions', json=edit).status_code == 409
    response = client.post(route + '/versions', json={**edit, 'confirm_replace_approved': True})
    assert response.status_code == 201
    second = client.get(route).json()['current']
    assert second['version'] == 2 and second['status'] == 'draft'
    assert client.get(route + '/approved').status_code == 409
    assert (data / 'projects' / project['id'] / 'script/script_v1.txt').read_text() == first['text']
    assert client.post(route + f'/versions/{first["id"]}/approve', json={'confirm': True}).status_code == 409
    assert client.post(route + f'/versions/{first["id"]}/select', json={'confirm_replace_approved': False}).status_code == 200
    assert client.get(route + '/approved').json()['id'] == first['id']
    assert client.post(route + f'/versions/{second["id"]}/select', json={'confirm_replace_approved': False}).status_code == 409
    assert client.post(route + f'/versions/{second["id"]}/select', json={'confirm_replace_approved': True}).status_code == 200
    assert client.post(route + '/versions', json=edit).status_code == 409  # stale editor base


def test_provider_switching_preserves_versions(studio):
    client, project, _, _ = studio
    for provider in ('gemini', 'openai', 'ollama'):
        view = run(studio, {'provider': provider})
        assert view['current']['provider'] == provider
    versions = client.get(f'/api/projects/{project["id"]}/script').json()['versions']
    assert [version['provider'] for version in versions] == ['ollama', 'openai', 'gemini']
    assert [version['version'] for version in versions] == [3, 2, 1]


def test_restart_persists_approved_script_and_versions(studio):
    client, project, _, data = studio
    version = run(studio)['current']
    route = f'/api/projects/{project["id"]}/script'
    client.post(route + f'/versions/{version["id"]}/approve', json={'confirm': True})
    with TestClient(create_app(data)) as restarted:
        restored = restarted.get(route + '/approved').json()
        assert restored['text'] == version['text']
        assert restored['status'] == 'approved'
        assert restored['created_at'] == version['created_at']


def test_owned_translation_is_separate_segmented_and_requires_ownership(studio):
    client, project, fake, _ = studio
    route = f'/api/projects/{project["id"]}/script/generate'
    assert client.post(route, json={'provider': 'gemini', 'mode': 'translate_owned', 'owned_text': 'My text.'}).status_code == 422
    assert client.post(route, json={'provider': 'gemini', 'mode': 'translate_owned', 'owned_text': 'My text.', 'owns_text': True, 'reference_text': 'Competitor text'}).status_code == 422
    source = ' '.join(f'Word{i}' for i in range(1000))
    view = run(studio, {'mode': 'translate_owned', 'owned_text': source, 'owns_text': True})
    assert view['current']['mode'] == 'translate_owned'
    assert view['current']['language'] == 'de'
    tasks = [task for task, _, _ in fake.calls]
    assert 'concept' not in tasks and 'plan' not in tasks
    translated = [data for task, data, _ in fake.calls if task == 'translate_owned']
    assert len(translated) == 3
    assert ' '.join(data['source_segment'] for data in translated) == source
    assert all(data['explicit_user_ownership_confirmed'] for data in translated)


@pytest.mark.parametrize('payload', [{'provider': 'website'}, {'words_per_minute_min': 200, 'words_per_minute_max': 100}, {'words_per_minute_min': 0}, {'api_key': KEY}, {'owned_text': 'text'}, {'reference_text': KEY}])
def test_invalid_input_is_turkish_and_no_secret_or_network(studio, payload):
    client, project, fake, _ = studio
    response = client.post(f'/api/projects/{project["id"]}/script/generate', json={'provider': 'gemini', **payload})
    assert response.status_code == 422
    assert KEY not in response.text
    assert not fake.calls


def test_repetition_check_and_target_duration():
    paragraph = 'Das ist ein ausführlicher Absatz mit ausreichend vielen Wörtern für eine erkennbare Wiederholung im ganzen Text.'
    assert repetition_warnings(paragraph + '\n\n' + paragraph)
    assert not repetition_warnings(paragraph)
    options = {'words_per_minute_min': 125, 'words_per_minute_max': 145}
    result = duration_metrics(' '.join(['Wort'] * 2700), 20, options)
    assert result == {'word_count': 2700, 'target_minutes': 20, 'target_word_min': 2500, 'target_word_max': 2900, 'estimated_minutes': 20, 'estimated_min_minutes': 18.62, 'estimated_max_minutes': 21.6}
    assert word_count('Straße weiß für E-Auto YouTube’s Test') == 6


def test_active_generation_blocks_duplicate_edit_delete_and_approval(studio):
    client, project, fake, _ = studio
    started, release = Event(), Event()
    original = fake.generate_script
    def blocking(prompt):
        started.set()
        assert release.wait(5)
        return original(prompt)
    fake.generate_script = blocking
    route = f'/api/projects/{project["id"]}/script'
    response = client.post(route + '/generate', json={'provider': 'gemini'})
    assert started.wait(3)
    try:
        assert client.post(route + '/generate', json={'provider': 'gemini'}).status_code == 409
        assert client.request('DELETE', f'/api/projects/{project["id"]}', json={'confirm': True}).status_code == 409
        assert client.get('/api/health').status_code == 200
        assert client.get(route).json()['job']['status'] in ('queued', 'analyzing')
    finally:
        release.set()
    client.app.state.scripts.futures[response.json()['job_id']].result(timeout=5)


def test_deleted_project_cascades_only_its_scripts(studio):
    client, project, _, data = studio
    run(studio)
    other = client.post('/api/projects', json={'name': 'Keep', 'topic': 'keep'}).json()
    response = client.request('DELETE', f'/api/projects/{project["id"]}', json={'confirm': True})
    assert response.status_code == 200
    assert client.get(f'/api/projects/{other["id"]}').status_code == 200
    with closing(sqlite3.connect(data / 'app.db')) as connection:
        assert connection.execute('SELECT COUNT(*) FROM script_versions').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM script_jobs').fetchone()[0] == 0


def test_schema3_upgrade_preserves_projects_and_creates_only_script_tables(tmp_path):
    with closing(sqlite3.connect(tmp_path / 'app.db')) as connection, connection:
        connection.execute('CREATE TABLE app_metadata (key TEXT PRIMARY KEY,value TEXT)')
        connection.execute("INSERT INTO app_metadata VALUES('schema_version','3')")
        connection.execute(PROJECT_SCHEMA)
        connection.execute('CREATE TABLE personal_data(value TEXT)')
        connection.execute("INSERT INTO personal_data VALUES('keep')")
    initialize_database(tmp_path)
    initialize_database(tmp_path)
    with closing(sqlite3.connect(tmp_path / 'app.db')) as connection:
        assert connection.execute('SELECT value FROM personal_data').fetchone()[0] == 'keep'
        assert connection.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] == '5'
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='script_versions'").fetchone()


@pytest.mark.parametrize('provider_type', ['gemini', 'openai', 'ollama'])
def test_verified_provider_generation_with_mock_api(provider_type):
    calls = []
    def respond(request):
        calls.append(request)
        body = json.loads(request.content)
        if provider_type == 'gemini':
            assert request.url.host == 'generativelanguage.googleapis.com'
            assert request.headers['x-goog-api-key'] == KEY
            return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'Natürliches Deutsch ' + KEY}]}}]})
        if provider_type == 'openai':
            assert str(request.url) == 'https://api.openai.com/v1/chat/completions'
            assert request.headers['authorization'] == 'Bearer ' + KEY
            assert body['messages'][-1]['content'] == 'Test prompt'
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': 'Natürliches Deutsch ' + KEY}}]})
        assert str(request.url) == 'http://127.0.0.1:11434/api/generate'
        assert body['prompt'] == 'Test prompt' and body['stream'] is False
        return httpx.Response(200, json={'done': True, 'done_reason': 'stop', 'response': 'Natürliches Deutsch'})
    transport = httpx.MockTransport(respond)
    provider = GeminiScriptProvider(KEY, MODEL, transport=transport) if provider_type == 'gemini' else OpenAIScriptProvider(KEY, MODEL, transport=transport) if provider_type == 'openai' else OllamaScriptProvider('http://127.0.0.1:11434', MODEL, transport=transport)
    assert isinstance(provider, ScriptProvider)
    result = provider.generate_script('Test prompt')
    assert 'Natürliches Deutsch' in result
    assert KEY not in result
    assert len(calls) == 1
    assert KEY not in str(calls[0].url)


@pytest.mark.parametrize('status', [401, 403, 404, 429, 500])
@pytest.mark.parametrize('provider_type', ['openai', 'ollama'])
def test_new_provider_errors_hide_raw_body(status, provider_type):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json={'error': KEY}))
    provider = OpenAIScriptProvider(KEY, MODEL, transport=transport) if provider_type == 'openai' else OllamaScriptProvider('http://localhost:11434', MODEL, transport=transport)
    with pytest.raises(ScriptProviderError) as error:
        provider.generate_script('Test')
    assert KEY not in str(error.value)


def test_gemini_api_drives_whole_engine_with_official_mock_contract(studio):
    client, _, fake, _ = studio
    requests = []
    def respond(request):
        requests.append(request)
        prompt = json.loads(request.content)['contents'][0]['parts'][0]['text']
        assert KEY not in prompt
        assert request.headers['x-goog-api-key'] == KEY
        result = fake.generate_script(prompt)
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': result}]}}]})
    client.app.state.scripts.provider_factory = lambda name, service: GeminiScriptProvider(KEY, MODEL, transport=httpx.MockTransport(respond))
    view = run(studio)
    assert view['current']['status'] == 'draft'
    assert len(requests) == 5
    assert all(request.url.host == 'generativelanguage.googleapis.com' for request in requests)


def test_cross_provider_secrets_never_reach_prompts_database_files_or_logs(studio, caplog):
    client, project, fake, data = studio
    original = fake.generate_script
    def echo(prompt):
        assert KEY not in prompt and OTHER_KEY not in prompt
        text = original(prompt)
        return text + ' ' + KEY + ' ' + OTHER_KEY if prompt.startswith('TASK: section') else text
    fake.generate_script = echo
    caplog.set_level('INFO')
    view = run(studio)
    assert view['current'] and '[gizlendi]' in view['current']['text']
    assert KEY not in json.dumps(view) + caplog.text
    assert OTHER_KEY not in json.dumps(view) + caplog.text
    with closing(sqlite3.connect(data / 'app.db')) as connection:
        dump = '\n'.join(connection.iterdump())
        assert KEY not in dump and OTHER_KEY not in dump
    for path in (data / 'projects' / project['id'] / 'script').iterdir():
        assert KEY not in path.read_text() and OTHER_KEY not in path.read_text()


def test_unexpected_provider_failure_is_safe_and_resumable(studio, caplog):
    _, _, fake, _ = studio
    def explode(prompt):
        raise RuntimeError(KEY + ' secret raw Google body stack')
    fake.generate_script = explode
    caplog.set_level('INFO')
    view = run(studio)
    assert view['job']['status'] == 'error'
    assert KEY not in json.dumps(view) + caplog.text
    assert 'raw Google body' not in json.dumps(view) + caplog.text
    assert 'Traceback' not in caplog.text


def test_reference_wording_cannot_escape_into_generated_text(studio):
    _, _, fake, _ = studio
    source = ' '.join(f'Quellwort{i}' for i in range(30))
    original = fake.generate_script
    def copying(prompt):
        return source if prompt.startswith('TASK: section') else original(prompt)
    fake.generate_script = copying
    view = run(studio, {'reference_text': source})
    assert view['job']['status'] == 'error'
    assert view['current'] is None
    assert 'Özgünlük' in view['job']['error_message']


def test_file_mirror_failure_keeps_completed_section_in_sqlite(studio, monkeypatch):
    client, project, fake, _ = studio
    repository = client.app.state.scripts.repository
    original = repository._file
    def failing(project_id, name, content):
        if name == 'generation_progress.json' and json.loads(content).get('sections'):
            from app.scripts.models import ScriptError
            raise ScriptError('Dosya kopyası yazılamadı.')
        return original(project_id, name, content)
    monkeypatch.setattr(repository, '_file', failing)
    view = run(studio)
    assert view['job']['status'] == 'error' and view['job']['completed_sections'] == 1
    assert view['job']['partial_text']
    monkeypatch.setattr(repository, '_file', original)
    job_id = view['job']['id']
    response = client.post(f'/api/projects/{project["id"]}/script/jobs/{job_id}/resume', json={'confirm_replace_approved': False})
    assert response.status_code == 202
    client.app.state.scripts.futures[job_id].result(timeout=5)
    assert client.get(f'/api/projects/{project["id"]}/script').json()['current']
    assert sum(task == 'section' for task, _, _ in fake.calls) == 1


def test_restart_marks_incomplete_jobs_recoverable_without_automatic_provider_calls(studio):
    client, project, fake, data = studio
    view = run(studio)
    job_id = view['job']['id']
    with closing(sqlite3.connect(data / 'app.db')) as connection, connection:
        connection.execute("UPDATE script_jobs SET status='generating' WHERE id=?", (job_id,))
    calls_before = len(fake.calls)
    with TestClient(create_app(data), headers=HEADERS) as restarted:
        restarted.app.state.scripts.provider_factory = lambda name, settings: fake
        recovered = restarted.get(f'/api/projects/{project["id"]}/script').json()
        assert recovered['job']['status'] == 'error'
        assert 'uygulama kapatıldığı' in recovered['job']['error_message']
        assert len(fake.calls) == calls_before
        response = restarted.post(f'/api/projects/{project["id"]}/script/jobs/{job_id}/resume', json={'confirm_replace_approved': False})
        assert response.status_code == 202
        restarted.app.state.scripts.futures[job_id].result(timeout=5)
        assert len(restarted.get(f'/api/projects/{project["id"]}/script').json()['versions']) == 1


@pytest.mark.parametrize('provider', ['gemini', 'openai', 'ollama'])
def test_script_providers_optional_without_keys(tmp_path, provider):
    with TestClient(create_app(tmp_path), headers=HEADERS) as client:
        project = client.post('/api/projects', json={'name': 'Optional', 'topic': 'topic'}).json()
        response = client.post(f'/api/projects/{project["id"]}/script/generate', json={'provider': provider})
        assert response.status_code == 422
        assert client.get('/api/health').status_code == 200
        assert client.get(f'/api/projects/{project["id"]}/script').json()['job'] is None


def test_resume_rejects_changed_model(studio):
    client, project, fake, _ = studio
    fake.fail = lambda task, data: task == 'section'
    view = run(studio)
    client.app.state.settings.save('gemini', {'api_key': 'replacement-only-key-7777'})
    settings = client.app.state.settings
    settings.record_gemini_models(settings.gemini_config(), ['different-model'])
    settings.save('gemini', {'model': 'different-model'})
    response = client.post(f'/api/projects/{project["id"]}/script/jobs/{view["job"]["id"]}/resume', json={'confirm_replace_approved': False})
    assert response.status_code == 409
    assert 'Model önceki üretimden farklı' in response.text


def test_script_mutations_require_local_origin_and_header(studio):
    client, project, _, _ = studio
    route = f'/api/projects/{project["id"]}/script/generate'
    assert client.post(route, json={'provider': 'gemini'}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.post(route, json={'provider': 'gemini'}, headers={'X-AI-Video-Studio': ''}).status_code == 403
    assert client.get(f'/api/projects/{project["id"]}/script').headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('key', ['quoted-key-"-1234', 'slash-key-\\-1234', 'url-key-/-1234'])
def test_secret_guard_handles_nested_and_encoded_values(key):
    from app.scripts.models import ScriptError
    guard = SecretGuard([key])
    with pytest.raises(ScriptError):
        guard.validate({'outer': [{'inner': key}]})
    assert key not in guard.clean({'inner': key})['inner']
    escaped = json.dumps(key, ensure_ascii=False)[1:-1]
    assert escaped not in guard.clean(escaped)


@pytest.mark.parametrize('bad_result', ['not JSON', '{"sections":[]}', '{"sections":[{"title":"Entire long video","purpose":"whole","target_words":3000}]}'])
def test_bad_or_giant_plan_is_safe_and_resume_preserves_analysis(studio, bad_result):
    _, _, fake, _ = studio
    original = fake.generate_script
    fake.generate_script = lambda prompt: bad_result if prompt.startswith('TASK: plan') else original(prompt)
    view = run(studio)
    assert view['job']['status'] == 'error'
    assert view['job']['progress']['blueprint']
    assert not view['current']


@pytest.mark.parametrize('provider_type', ['openai', 'ollama'])
@pytest.mark.parametrize('kind', ['timeout', 'redirect', 'incomplete', 'invalid_json'])
def test_optional_provider_network_and_incomplete_errors_safe(provider_type, kind):
    calls = []
    def respond(request):
        calls.append(request)
        if kind == 'timeout':
            raise httpx.ReadTimeout(KEY, request=request)
        if kind == 'redirect':
            return httpx.Response(302, headers={'Location': 'https://evil.example'})
        if kind == 'invalid_json':
            return httpx.Response(200, text=KEY)
        return httpx.Response(200, json={'choices': [{'finish_reason': 'length', 'message': {'content': KEY}}]} if provider_type == 'openai' else {'done': True, 'done_reason': 'length', 'response': KEY})
    transport = httpx.MockTransport(respond)
    provider = OpenAIScriptProvider(KEY, MODEL, transport=transport) if provider_type == 'openai' else OllamaScriptProvider('http://localhost:11434', MODEL, transport=transport)
    with pytest.raises(ScriptProviderError) as error:
        provider.generate_script('Test')
    assert KEY not in str(error.value)
    assert len(calls) == 1


def test_script_file_symlink_does_not_touch_other_locations(studio):
    client, project, _, data = studio
    directory = data / 'projects' / project['id'] / 'script'
    directory.rmdir()
    external = data.parent / 'external'
    external.mkdir(); (external / 'keep.txt').write_text('keep')
    try:
        directory.symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('Symlink creation is unavailable')
    view = run(studio)
    assert view['job']['status'] == 'error'
    assert (external / 'keep.txt').read_text() == 'keep'
    assert list(external.iterdir()) == [external / 'keep.txt']


def test_part4_schema_upgrade_failure_rolls_back(tmp_path):
    with closing(sqlite3.connect(tmp_path / 'app.db')) as connection, connection:
        connection.execute('CREATE TABLE app_metadata (key TEXT PRIMARY KEY,value TEXT)')
        connection.execute("INSERT INTO app_metadata VALUES('schema_version','3')")
        connection.execute(PROJECT_SCHEMA)
        connection.execute('CREATE TABLE script_versions (legacy TEXT)')
        connection.execute("INSERT INTO script_versions VALUES('keep')")
    with pytest.raises(sqlite3.Error):
        initialize_database(tmp_path)
    with closing(sqlite3.connect(tmp_path / 'app.db')) as connection:
        assert connection.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] == '3'
        assert connection.execute('SELECT legacy FROM script_versions').fetchone()[0] == 'keep'
        assert not connection.execute("SELECT name FROM sqlite_master WHERE name='script_jobs'").fetchone()
