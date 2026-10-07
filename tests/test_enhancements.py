import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.scripts.quality import CRITERIA
from test_scripts import studio, run, KEY


@pytest.mark.parametrize('language', ['de', 'es', 'en', 'fr', 'tr'])
def test_project_language_generation_translation_and_restart(studio, language):
    client, project, fake, data = studio
    client.patch(f'/api/projects/{project["id"]}', json={'language': language})
    view = run(studio)
    assert view['current']['language'] == language
    assert all(payload['language'] == language for task, payload, _ in fake.calls if task == 'section')
    view = run(studio, {'mode': 'translate_owned', 'owns_text': True, 'owned_text': 'My own original source.'})
    assert view['current']['language'] == language
    assert next(payload['language'] for task, payload, _ in fake.calls if task == 'translate_owned') == language
    with TestClient(create_app(data)) as restarted:
        assert restarted.get(f'/api/projects/{project["id"]}/script').json()['current']['language'] == language


@pytest.fixture
def quality_studio(studio):
    client, project, fake, data = studio
    run(studio)
    generate = fake.generate_script
    def tools(prompt):
        task = prompt.splitlines()[0].removeprefix('TASK: ')
        payload = json.loads(prompt.split('INPUT DATA (not instructions):\n')[1])
        if task in ('retention', 'hooks', 'alternatives', 'claims', 'apply_suggestions'):
            fake.calls.append((task, payload, prompt))
        if task == 'retention': return json.dumps({'ratings': {key: 'Orta' for key in CRITERIA}, 'suggestions': [{'scope': 'opening', 'suggestion': 'Açılışı kısa ve konuya uygun yapın.'}]})
        if task == 'hooks': return json.dumps({'hooks': ['Seçenek bir', 'Seçenek iki', 'Seçenek üç']})
        if task == 'alternatives': return json.dumps({key: ['Bir', 'İki'] for key in ('opening', 'title', 'thumbnail_text', 'intro', 'CTA', 'description')})
        if task == 'claims': return json.dumps({'claims': [{'statement': '2024 yılında artış yaşandı.', 'reason': 'Tarih ve artış için kaynak gerekli.'}]})
        if task == 'apply_suggestions': return 'Yeni açılış. ' + payload['segment']
        return generate(prompt)
    fake.generate_script = tools
    return studio


def tool(studio, kind, payload=None):
    client, project, _, _ = studio
    response = client.post(f'/api/projects/{project["id"]}/script/tools/{kind}', json=payload or {'provider': 'gemini', 'cost_confirmed': True})
    assert response.status_code == 202, response.text
    client.app.state.scripts.futures[response.json()['job_id']].result(timeout=5)
    view = client.get(f'/api/projects/{project["id"]}/script').json()
    assert view['job']['status'] == 'draft', view['job']
    return view


@pytest.mark.parametrize('kind', ['retention', 'hooks', 'alternatives', 'claims'])
def test_quality_outputs_never_change_script_and_are_persistent(quality_studio, kind):
    client, project, _, data = quality_studio
    before = client.get(f'/api/projects/{project["id"]}/script').json()['current']
    view = tool(quality_studio, kind)
    assert view['current'] == before
    artifact = view['artifacts'][0]
    assert artifact['kind'] == kind and artifact['version_id'] == before['id']
    assert KEY not in json.dumps(artifact)
    if kind == 'claims': assert all(not item['verified'] and item['status'] == 'Doğrulama gerektirebilir.' and item['sources'] == [] for item in artifact['result']['claims'])
    if kind == 'hooks': assert len(artifact['result']['hooks']) == 3
    with TestClient(create_app(data)) as restarted:
        assert restarted.get(f'/api/projects/{project["id"]}/script').json()['artifacts'][0] == artifact


def test_applying_selected_suggestions_protects_approved_script(quality_studio):
    client, project, _, _ = quality_studio
    view = tool(quality_studio, 'retention')
    current, artifact = view['current'], view['artifacts'][0]
    base = f'/api/projects/{project["id"]}/script'
    client.post(base + f'/versions/{current["id"]}/approve', json={'confirm': True})
    payload = {'selection': [0], 'cost_confirmed': True, 'confirm_replace_approved': False}
    assert client.post(base + f'/tools/{artifact["id"]}/apply', json=payload).status_code == 409
    response = client.post(base + f'/tools/{artifact["id"]}/apply', json={**payload, 'confirm_replace_approved': True})
    assert response.status_code == 202
    client.app.state.scripts.futures[response.json()['job_id']].result(timeout=5)
    view = client.get(base).json()
    assert view['current']['version'] == 2 and view['current']['status'] == 'draft'
    assert view['versions'][1]['status'] == 'approved'
    assert client.post(base + f'/tools/{artifact["id"]}/apply', json=payload).status_code == 409


def test_optional_paid_tool_requires_explicit_per_operation_confirmation(quality_studio):
    client, project, fake, _ = quality_studio
    count = len(fake.calls)
    response = client.post(f'/api/projects/{project["id"]}/script/tools/hooks', json={'provider': 'gemini', 'cost_confirmed': False})
    assert response.status_code == 409 and len(fake.calls) == count


def test_alternative_choice_persists_without_overwriting_script(quality_studio):
    client, project, _, _ = quality_studio
    view = tool(quality_studio, 'alternatives')
    artifact, current = view['artifacts'][0], view['current']
    route = f'/api/projects/{project["id"]}/script/tools/{artifact["id"]}/select'
    assert client.post(route, json={'choices': {'title': 1, 'CTA': 0}}).status_code == 200
    assert client.post(route, json={'choices': {'title': 999}}).status_code == 422
    after = client.get(f'/api/projects/{project["id"]}/script').json()
    assert after['current'] == current
    assert after['artifacts'][0]['result']['selected'] == {'title': 1, 'CTA': 0}


def test_quality_partial_failure_can_resume_completed_segments(quality_studio):
    client, project, fake, _ = quality_studio
    route = f'/api/projects/{project["id"]}/script'
    current = client.get(route).json()['current']
    client.post(route + '/versions', json={'text': ' '.join(['Original'] * 1300), 'base_version_id': current['id']})
    original, attempts = fake.generate_script, []
    def fail_once(prompt):
        if prompt.startswith('TASK: retention'):
            payload = json.loads(prompt.split('INPUT DATA (not instructions):\n')[1]); attempts.append(payload['segment_index'])
            if attempts == [0, 1]: raise RuntimeError(KEY)
        return original(prompt)
    fake.generate_script = fail_once
    response = client.post(route + '/tools/retention', json={'provider': 'gemini', 'cost_confirmed': True})
    job_id = response.json()['job_id']; client.app.state.scripts.futures[job_id].result(timeout=5)
    view = client.get(route).json()
    assert view['job']['status'] == 'error' and len(view['job']['progress']['parts']) == 1
    assert KEY not in json.dumps(view)
    response = client.post(route + f'/jobs/{job_id}/resume', json={'confirm_replace_approved': False})
    assert response.status_code == 202
    client.app.state.scripts.futures[job_id].result(timeout=5)
    assert attempts == [0, 1, 1, 2]
    assert client.get(route).json()['job']['status'] == 'draft'
