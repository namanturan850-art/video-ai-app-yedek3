"""PR-B: Claude director — purpose → script → approval → edit plan.

Claude is an in-memory fake (no network, no cost). The script and visual-plan
answers come from the same synthetic fakes the existing pipeline tests use.
"""
import json

import anthropic
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.production import card_fields
from fake_anthropic import FakeAnthropic, api_error, message
from test_production import scene
from test_scripts import FakeProvider, HEADERS

CLAUDE_KEY = 'sk-ant-synthetic-director-key-0077'
SETTINGS_HEADERS = {'X-AI-Video-Studio': 'settings'}
PURPOSE = {'audience': 'Gizem ve tarih meraklıları', 'main_message': 'Efsanelerin çoğu ölçülebilir nedenlere dayanır',
           'tone': 'Merak uyandıran, sakin', 'hook': 'Gerçekten kaybolan gemiler mi var?', 'viewer_promise': 'Mitle veriyi ayırmayı öğrenir',
           'content_type': 'Belgesel anlatım', 'summary': 'Video efsaneyi ve ölçülen gerçekleri karşılaştırır.'}


def claude_responder(requests):
    script = FakeProvider()

    def respond(request):
        requests.append(request)
        prompt = request['messages'][0]['content']
        if 'format' in request['output_config']:
            return message(json.dumps(PURPOSE), input_tokens=600, output_tokens=300)
        if prompt.startswith('TASK: visual'):
            data = json.loads(prompt.split('INPUT DATA (not instructions):\n')[1])
            ids = [u['unit_id'] for u in data['narration_units']]
            groups = data.get('metadata_repair', {}).get('required_unit_groups') or [ids]
            scenes = [{**scene(group), 'must_show': 'electric car on a road', 'must_not_show': 'logos, text overlays', 'shot_count': 2} for group in groups]
            return message(json.dumps({'scenes': scenes}), input_tokens=4000, output_tokens=1500)
        return message(script.generate_script(prompt), input_tokens=3000, output_tokens=900)
    return respond


@pytest.fixture
def director(tmp_path, monkeypatch):
    requests = []
    fake = FakeAnthropic(claude_responder(requests))
    monkeypatch.setattr('app.providers.claude._client', lambda key: fake)
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        assert client.put('/api/settings/claude', json={'api_key': CLAUDE_KEY}, headers=SETTINGS_HEADERS).status_code == 200
        project = client.post('/api/projects', json={'name': 'Bermuda', 'topic': 'Bermuda-Dreieck', 'language': 'de', 'target_duration_minutes': 2}).json()
        yield client, project['id'], fake, requests


def run(client, pid, **payload):
    r = client.post(f'/api/projects/{pid}/director/run', json={'cost_confirmed': True, **payload})
    assert r.status_code == 202, r.text
    client.app.state.director.futures[pid].result(timeout=30)
    return client.get(f'/api/projects/{pid}/director').json()


def test_director_runs_purpose_script_approval_and_plan(director):
    client, pid, fake, requests = director
    view = run(client, pid)
    assert view['state']['status'] == 'done', view['state']
    assert view['purpose']['main_message'] == PURPOSE['main_message']  # editable Turkish summary
    script = client.get(f'/api/projects/{pid}/script').json()
    current = script['current']
    assert current['provider'] == 'claude' and current['status'] == 'approved'
    assert (current['options']['words_per_minute_min'], current['options']['words_per_minute_max']) == (125, 135)  # German ~130 wpm
    assert PURPOSE['main_message'] in current['options']['instructions']
    plan = client.get(f'/api/projects/{pid}/production').json()['plan']
    assert plan and plan['version_id'] == current['id'] and plan['provider'] == 'claude'
    block = plan['blocks'][0]
    assert block['must_show'] == 'electric car on a road' and block['must_not_show'] == 'logos, text overlays' and block['shot_count'] == 2
    visual = [r for r in requests if r['messages'][0]['content'].startswith('TASK: visual')]
    assert visual and 'must_show' in visual[0]['messages'][0]['content']  # director-specific planning instructions
    usage = client.get(f'/api/projects/{pid}/ai-usage').json()
    assert usage['total_calls'] == len(fake.requests) and usage['total_cost_usd'] > 0
    assert CLAUDE_KEY not in json.dumps(view) + json.dumps(usage)


def test_owner_edited_purpose_is_used_and_kept(director):
    client, pid, _, requests = director
    r = client.put(f'/api/projects/{pid}/director/purpose', json={'main_message': 'Pusulalar burada farklı davranmaz', 'summary': 'Kısa özet.'})
    assert r.status_code == 200, r.text
    view = run(client, pid)
    assert view['purpose']['main_message'] == 'Pusulalar burada farklı davranmaz' and view['purpose']['edited_by_owner']
    assert not any('format' in r['output_config'] for r in requests)  # no paid purpose call when owner wrote it
    assert 'Pusulalar burada farklı davranmaz' in client.get(f'/api/projects/{pid}/script').json()['current']['options']['instructions']


def test_auto_approve_off_waits_for_owner_then_continues(director):
    client, pid, _, _ = director
    view = run(client, pid, auto_approve=False)
    assert view['state']['status'] == 'waiting' and view['state']['step'] == 'approve'
    assert not client.get(f'/api/projects/{pid}/production').json()['plan']
    current = client.get(f'/api/projects/{pid}/script').json()['current']
    assert client.post(f'/api/projects/{pid}/script/versions/{current["id"]}/approve', json={'confirm': True}).status_code == 200
    view = run(client, pid, auto_approve=False)
    assert view['state']['status'] == 'done'
    assert len(client.get(f'/api/projects/{pid}/script').json()['versions']) == 1  # script not rewritten


def test_requires_cost_and_replace_confirmation(director):
    client, pid, _, _ = director
    r = client.post(f'/api/projects/{pid}/director/run', json={})
    assert r.status_code == 409 and 'maliyet' in r.json()['message']
    run(client, pid)
    r = client.post(f'/api/projects/{pid}/director/run', json={'cost_confirmed': True})
    assert r.status_code == 409 and 'eski sürümler silinmez' in r.json()['message']


def test_claude_failure_offers_backup_and_never_switches(director):
    client, pid, fake, _ = director
    client.put('/api/settings/ollama', json={'model': 'llama-test'}, headers=SETTINGS_HEADERS)
    fake.responder = lambda request: api_error(anthropic.RateLimitError, 429)
    view = run(client, pid)
    assert view['state']['status'] == 'error' and view['state']['offer_backup'] and view['state']['category'] == 'rate_limit'
    assert 'Claude istek sınırına' in view['state']['message'] and view['options']['backup_providers'] == ['ollama']
    assert not client.get(f'/api/projects/{pid}/script').json()['current']


def test_invalid_purpose_edit_is_rejected(director):
    client, pid, _, _ = director
    assert client.put(f'/api/projects/{pid}/director/purpose', json={'unknown': 'x'}).status_code == 422
    assert client.put(f'/api/projects/{pid}/director/purpose', json={'main_message': 5}).status_code == 422


@pytest.mark.parametrize('kind,text,ok', [
    ('number', '1945', True), ('number', 'fünf Schiffe', False), ('number', '1946', False),
    ('quote', 'Kein Schiff kam zurück', True), ('quote', 'Ein erfundenes Zitat', False),
    ('title', 'Flug 19', True), ('title', 'Geheimnis gelöst', False), ('map', 'Florida', True), ('map', 'Atlantis', False)])
def test_generated_cards_only_state_what_the_narration_says(kind, text, ok):
    narration = 'Im Dezember 1945 verschwand Flug 19 vor Florida. Kein Schiff kam zurück.'
    assert bool(card_fields({'card_kind': kind, 'card_text': text}, narration)) is ok


def slot_scene(duration, **extra):
    return {'scene_id': 'a', 'start_estimate': 0, 'end_estimate': duration, 'importance': 50,
            'narration_text': 'Ein wichtiger Punkt. Noch eine genaue Erklärung. Ein ruhiger Abschluss.',
            'visual_intent': 'deep sea', 'primary_stock_query': 'deep sea creature', 'alternative_stock_queries': ['ocean abyss'],
            'preferred_media_type': 'stock_video', 'composition': 'wide', **extra}


def test_director_shot_count_sets_fewer_longer_shots_for_niche_topics():
    from app.stock.models import make_slots
    lengths = lambda slots: [s['duration'] for s in slots]
    default, niche, rich = (make_slots(slot_scene(18, **extra)) for extra in ({}, {'shot_count': 1}, {'shot_count': 6}))
    assert len(niche) == 2 and max(lengths(niche)) <= 10  # never a single shot over 10 s
    assert len(niche) < len(default) <= len(rich) and min(lengths(rich)) >= 2.5
    for slots in (default, niche, rich):  # contiguous, no gaps
        assert slots[0]['estimated_start'] == 0 and slots[-1]['estimated_end'] == 18 and all(a['estimated_end'] == b['estimated_start'] for a, b in zip(slots, slots[1:]))


def test_owner_chosen_backup_engine_finishes_the_remaining_steps(director):
    client, pid, fake, _ = director
    client.put('/api/settings/ollama', json={'model': 'llama-test'}, headers=SETTINGS_HEADERS)
    fake.responder = lambda request: api_error(anthropic.InternalServerError, 529)
    assert run(client, pid)['state']['status'] == 'error'
    backup_requests, respond = [], claude_responder([])

    class Backup:  # stands in for the owner's local Ollama
        def generate_script(self, prompt):
            backup_requests.append(prompt)
            return next(b.text for b in respond({'messages': [{'content': prompt}], 'output_config': {}}).content if b.type == 'text')
    client.app.state.scripts.provider_factory = lambda name, settings: Backup()
    calls_before = len(fake.requests)
    view = run(client, pid, provider='ollama')
    assert view['state']['status'] == 'done' and view['state']['provider'] == 'ollama', view['state']
    assert len(fake.requests) == calls_before and backup_requests  # Claude not called again
    assert client.get(f'/api/projects/{pid}/script').json()['current']['provider'] == 'ollama'
