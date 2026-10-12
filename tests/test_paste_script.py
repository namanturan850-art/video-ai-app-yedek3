"""“Metni yapıştır”: the owner's own text is cleaned, saved as an approved
script version and goes word for word to narration and subtitles; markers
never do. AI script writing stays in the code behind a flag (default off)."""
import json

import httpx
import pytest

from app.narration.audio import AudioDownloader
from app.production import narration_units, visual_blocks
from app.scripts.paste import apply_markers, clean
from test_narration import FakeTTS, KEY as TTS_KEY, VOICE
from test_narration_foundation import wav_data
from test_production import scene as base_scene
from test_scripts import HEADERS, run, studio  # noqa: F401  (fixture)

RAW = """# Das Rätsel des Bermuda-Dreiecks
## Kapitel 1: Der Anfang

[GÖRSEL: airplane cockpit at night] Im Dezember 1945 startete **Flug 19** zu einem Übungsflug.   Niemand kam zurück.

- Das Gebiet liegt zwischen Florida, Bermuda und Puerto Rico. [HARİTA: Bermuda Triangle]
* Heute fahren dort jeden Tag Schiffe. [SAYI: %40] [NOTIZ: später prüfen]
"""
CLEAN = ('Im Dezember 1945 startete Flug 19 zu einem Übungsflug. Niemand kam zurück.\n\n'
         'Das Gebiet liegt zwischen Florida, Bermuda und Puerto Rico. Heute fahren dort jeden Tag Schiffe.')


def test_clean_removes_markdown_headings_and_reads_markers():
    result = clean(RAW)
    assert result['text'] == CLEAN and '[' not in result['text'] and '#' not in result['text'] and '**' not in result['text']
    assert [(m['label'], m['value'], m['sentence']) for m in result['markers']] == [
        ('GÖRSEL', 'airplane cockpit at night', 'Im Dezember 1945 startete Flug 19 zu einem Übungsflug.'),
        ('HARİTA', 'Bermuda Triangle', 'Das Gebiet liegt zwischen Florida, Bermuda und Puerto Rico.'),
        ('SAYI', '%40', 'Heute fahren dort jeden Tag Schiffe.')]
    assert len(result['warnings']) == 1 and 'NOTIZ' in result['warnings'][0]  # unknown marker: warning, still not spoken
    assert clean('1. Einleitung\nText eins.\n2) Zweiter Punkt hier.\nSzene 3\nEnde.')['text'] == 'Text eins. Zweiter Punkt hier.\n\nEnde.'


def project(client, name='Bermuda', language='de'):
    r = client.post('/api/projects', json={'name': name, 'language': language})
    assert r.status_code == 201, r.text  # title and language are enough
    return r.json()


def test_title_and_language_are_enough_and_estimate_uses_language_pace(studio):
    client = studio[0]
    p = project(client)
    assert p['topic'] == 'Bermuda'
    preview = client.post(f'/api/projects/{p["id"]}/script/paste/preview', json={'text': ' '.join(['Wort'] * 385)}).json()
    assert preview['word_count'] == 385 and preview['spoken_rate'] == 130 and 2.9 <= preview['estimated_minutes'] <= 3.0  # ~2:58, not 1,4


def test_paste_saves_approved_versions_and_keeps_raw_text(studio):
    client = studio[0]
    p = project(client)
    r = client.post(f'/api/projects/{p["id"]}/script/paste', json={'text': RAW})
    assert r.status_code == 201, r.text
    current = r.json()['current']
    assert current['text'] == CLEAN and current['status'] == 'approved' and current['raw_text'] == RAW and len(current['markers']) == 3
    assert client.get(f'/api/projects/{p["id"]}/script/approved').json()['text'] == CLEAN
    # Edit later → new version (explicit confirmation because one is approved); the old one stays.
    edited = RAW.replace('Niemand kam zurück.', 'Niemand kam je zurück.')
    assert client.post(f'/api/projects/{p["id"]}/script/paste', json={'text': edited}).status_code == 409
    view = client.post(f'/api/projects/{p["id"]}/script/paste', json={'text': edited, 'confirm_replace_approved': True}).json()
    assert view['current']['version'] == 2 and 'je zurück' in view['current']['text'] and len(view['versions']) == 2
    assert client.post(f'/api/projects/{p["id"]}/script/paste', json={'text': '[GÖRSEL: nur ein Hinweis]', 'confirm_replace_approved': True}).status_code == 422


def test_pasted_text_goes_word_for_word_to_narration_and_subtitles(studio):
    client = studio[0]
    p = project(client)
    current = client.post(f'/api/projects/{p["id"]}/script/paste', json={'text': RAW}).json()['current']
    settings = client.app.state.settings
    settings.save('ai33', {'api_key': TTS_KEY, 'voice_provider': 'edge', 'speed': 1.0})
    settings.record_tts_voices(settings.tts_config(), [VOICE]); settings.save('ai33', {'voice_id': VOICE['voice_id']})
    service = client.app.state.narration; fake = FakeTTS(); service.factory = lambda s: fake; service.poll_interval = .001
    service.downloader = AudioDownloader(service.projects, transport=httpx.MockTransport(lambda r: httpx.Response(200, headers={'Content-Type': 'audio/wav'}, content=wav_data())))
    r = client.post(f'/api/projects/{p["id"]}/narration/jobs', json={'source_script_version_id': current['id'], 'voice_provider': VOICE['provider'],
                                                                   'voice_id': VOICE['voice_id'], 'speed': 1.0, 'cost_confirmed': True})
    assert r.status_code == 202, r.text
    service.futures[r.json()['job_id']].result(timeout=8)
    assert fake.creations and fake.creations[0][0] == CLEAN  # exactly the pasted words, no markers
    assert '[' not in fake.creations[0][0] and 'airplane' not in fake.creations[0][0]
    subtitles = client.post(f'/api/projects/{p["id"]}/subtitles/versions', json={'regenerate_confirmed': False})
    assert subtitles.status_code in (200, 201), subtitles.text
    cues = client.get(f'/api/projects/{p["id"]}/subtitles').json()['active']['cues']
    assert ' '.join(c['text'] for c in cues).split() == CLEAN.split() and not any('[' in c['text'] for c in cues)


def test_markers_steer_the_scene_plan_without_touching_words(studio):
    client = studio[0]
    p = project(client)
    current = client.post(f'/api/projects/{p["id"]}/script/paste', json={'text': RAW}).json()['current']
    units = narration_units(current['text'])
    ids = [u['unit_id'] for u in units]
    blocks = visual_blocks({'scenes': [base_scene(ids[:2]), base_scene(ids[2:])]}, current['text'], 'de', 130, units=units)
    plan = client.app.state.production.save_generated(p['id'], current['id'], 'de', blocks)
    first, second = plan['blocks']
    assert first['stock_query'] == 'airplane cockpit at night' and [{k: h[k] for k in ('type', 'value')} for h in first['owner_hints']] == [{'type': 'visual', 'value': 'airplane cockpit at night'}]
    assert first['owner_hints'][0]['sentence'] == 'Im Dezember 1945 startete Flug 19 zu einem Übungsflug.'  # the graphic is timed to its sentence
    assert first['must_show'] == 'airplane cockpit at night'
    assert {h['type'] for h in second['owner_hints']} == {'map', 'number'} and 'Bermuda Triangle map' in second['alternative_stock_queries']
    assert ' '.join(b['narration'] for b in plan['blocks']).split() == CLEAN.split()  # words never change
    handoff = client.app.state.production.handoff(p['id'])
    assert handoff['scenes'][0]['owner_hints'][0]['value'] == 'airplane cockpit at night'
    assert apply_markers([{'narration': 'X.', 'stock_query': 'a', 'alternative_stock_queries': ['b']}], [{'type': 'visual', 'value': 'v', 'sentence': 'nicht da'}])[0]['stock_query'] == 'a'


def test_script_writing_is_hidden_by_default_and_old_projects_open(studio, monkeypatch):
    client = studio[0]
    old = run(studio)['current']  # an AI-written version from before
    page = client.get(f'/projects/{studio[1]["id"]}/script').text
    assert 'data-script-generation="0"' in page and '/static/paste.js' in page
    view = client.get(f'/api/projects/{studio[1]["id"]}/script/paste').json()
    assert view['current']['id'] == old['id'] and view['current']['raw_text'] == old['text'] and view['current']['markers'] == []
    js = {name: open(f'app/static/{name}', encoding='utf-8').read() for name in ('script.js', 'director.js', 'paste.js', 'projects.js', 'settings.js')}
    assert "document.body.dataset.scriptGeneration === '1'" in js['script.js'].split('\n', 3)[2]  # whole generator screen behind the flag
    assert "document.body.dataset.scriptGeneration === '1'" in js['director.js'].split('\n', 3)[2]
    assert "scriptGeneration !== '1'" in js['paste.js'].split('\n', 4)[2]
    assert 'if (GEN) detail.append(sourceCard(project));' in js['projects.js']
    monkeypatch.setenv('AVS_SCRIPT_GENERATION', '1')
    assert 'data-script-generation="1"' in client.get(f'/projects/{studio[1]["id"]}/script').text  # code kept, flag turns it on
