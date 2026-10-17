"""Stage 1: channels, “Tarzım” kit, sound effects, wizard, subtitle style. No network."""
from contextlib import closing
import json
import sqlite3
import struct
import wave
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient

from app.channels import DEFAULT_STYLE, PRESETS
from app.database import initialize_database, SCHEMA_VERSION
from app.main import create_app
from app.rendering import ass
from test_scripts import HEADERS

SETTINGS = {'X-AI-Video-Studio': 'settings'}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        yield client


def wav_bytes():
    out = BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(struct.pack('<h', 0) * 800)
    return out.getvalue()


def test_migration_puts_every_existing_project_in_a_default_channel(tmp_path):
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as c:
        ids = [c.post('/api/projects', json={'name': f'P{i}', 'topic': 'Rom'}).json()['id'] for i in range(3)]
    db = tmp_path / 'data' / 'app.db'
    with closing(sqlite3.connect(db)) as c, c:  # simulate an owner database still at schema 11
        c.execute('DROP TABLE channels'); c.execute('ALTER TABLE projects DROP COLUMN channel_id')
        c.execute("UPDATE app_metadata SET value='11' WHERE key='schema_version'")
    initialize_database(tmp_path / 'data')
    with closing(sqlite3.connect(db)) as c:
        assert c.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] == SCHEMA_VERSION
        default = c.execute('SELECT id,name FROM channels WHERE is_default=1').fetchall()
        assert len(default) == 1 and default[0][1] == 'Varsayılan kanal'
        assert {r[0] for r in c.execute('SELECT channel_id FROM projects')} == {default[0][0]}
        assert sorted(r[0] for r in c.execute('SELECT name FROM projects')) == ['P0', 'P1', 'P2']
    initialize_database(tmp_path / 'data')  # idempotent
    with closing(sqlite3.connect(db)) as c:
        assert c.execute('SELECT COUNT(*) FROM channels').fetchone()[0] == 1


def test_channel_crud_and_project_binding(client):
    channels = client.get('/api/channels').json()
    default = channels['channels'][0]
    assert default['is_default'] and default['style'] == DEFAULT_STYLE and {f['id'] for f in channels['options']['fonts']} >= {'inter', 'bebas'}
    r = client.post('/api/channels', json={'name': 'Gizem Kanalı', 'language': 'en', 'target_duration_minutes': 8, 'niche': 'mysteries',
                                           'voice_provider': 'elevenlabs', 'voice_id': 'elevenlabs_abc', 'voice_name': 'Anna', 'voice_speed': 1.1})
    assert r.status_code == 201, r.text
    ch = r.json()
    p = client.post('/api/projects', json={'name': 'X', 'topic': 'Bermuda', 'channel_id': ch['id'], 'language': 'en', 'target_duration_minutes': 8}).json()
    assert p['channel_id'] == ch['id'] and client.get(f'/api/projects/{p["id"]}').json()['channel_name'] == 'Gizem Kanalı'
    plain = client.post('/api/projects', json={'name': 'Y', 'topic': 'Rom'}).json()
    assert plain['channel_id'] == default['id']
    assert client.post('/api/projects', json={'name': 'Z', 'topic': 'Rom', 'channel_id': 'f' * 32}).status_code == 404
    assert client.delete(f'/api/channels/{ch["id"]}').status_code == 409          # has a project
    assert client.delete(f'/api/channels/{default["id"]}').status_code == 409     # default is permanent
    assert client.patch(f'/api/projects/{p["id"]}', json={'channel_id': default['id']}).status_code == 200
    assert client.delete(f'/api/channels/{ch["id"]}').status_code == 200


def test_style_kit_validation_rejects_unreadable_or_invalid_values(client):
    ch = client.get('/api/channels').json()['channels'][0]
    bad = [{'palette': {**DEFAULT_STYLE['palette'], 'accent': 'red'}}, {'motion_duration': 5},
           {'palette': {**DEFAULT_STYLE['palette'], 'background': '#FFFFFF', 'text': '#FAFAFA'}},  # no contrast
           {'heading_font': 'comic-sans'}, {'sfx': {'click': 'http://x', 'rise': 'none', 'hit': 'none'}}]
    for style in bad:
        assert client.put(f'/api/channels/{ch["id"]}', json={'style': style}).status_code == 422, style
    good = client.put(f'/api/channels/{ch["id"]}', json={'style': {'heading_font': 'bebas', 'easing': 'bounce', 'motion_duration': .4}}).json()
    assert good['style']['heading_font'] == 'bebas' and good['style']['palette'] == DEFAULT_STYLE['palette']


def test_sound_effects_default_upload_and_play(client):
    ch = client.get('/api/channels').json()['channels'][0]
    assert client.get(f'/api/channels/{ch["id"]}/sfx/click').content[:4] == b'RIFF'  # bundled default
    data = wav_bytes()
    r = client.post(f'/api/channels/{ch["id"]}/sfx/hit', content=data, headers={**HEADERS, 'X-File-Name': 'my-hit.wav'})
    assert r.status_code == 200 and r.json()['style']['sfx']['hit'].startswith('upload:')
    assert client.get(f'/api/channels/{ch["id"]}/sfx/hit').content == data
    assert client.post(f'/api/channels/{ch["id"]}/sfx/hit', content=b'not audio', headers={**HEADERS, 'X-File-Name': 'x.wav'}).status_code == 422
    assert client.post(f'/api/channels/{ch["id"]}/sfx/boom', content=data, headers={**HEADERS, 'X-File-Name': 'x.wav'}).status_code == 422
    client.put(f'/api/channels/{ch["id"]}', json={'style': {'sfx': {'click': 'none', 'rise': 'default:rise', 'hit': 'default:hit'}}})
    assert client.get(f'/api/channels/{ch["id"]}/sfx/click').status_code == 404


def test_wizard_uses_preset_without_ai_and_gemini_when_configured(client, monkeypatch):
    ch = client.get('/api/channels').json()['channels'][0]
    r = client.post(f'/api/channels/{ch["id"]}/style/suggest', json={'topic': 'Weltraum', 'audience': 'Jugendliche', 'feeling': 'enerjik'}).json()
    assert r['source'] == 'preset' and r['style']['palette'] == PRESETS['enerjik']['palette']
    s = client.app.state.settings
    s.save('gemini', {'api_key': 'synthetic-gemini-key-9999'}); s.record_gemini_models(s.gemini_config(), ['gemini-test']); s.save('gemini', {'model': 'gemini-test'})
    s.save('general', {'ai_visual_check': True})  # Gemini looks at the candidates (off by default)
    answers = [{'background': '#0A0A14', 'primary': '#FFFFFF', 'accent': '#00D1FF', 'text': '#FFFFFF', 'heading_font': 'oswald', 'body_font': 'inter',
                'motion_duration': 0.5, 'easing': 'snappy', 'subtitle_font': 'montserrat', 'subtitle_position': 'bottom', 'reason': 'Uzay için soğuk mavi vurgu.'},
               {'background': '#FFFFFF', 'primary': '#FFFFFF', 'accent': '#FFFFFF', 'text': '#FFFFFF', 'heading_font': 'x', 'body_font': 'y',
                'motion_duration': 9, 'easing': 'z', 'subtitle_font': 'q', 'subtitle_position': 'left', 'reason': ''}]
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': json.dumps(answers[len(seen) - 1])}]}, 'finishReason': 'STOP'}]})
    from app.providers import gemini
    class Patched(gemini.GeminiScriptProvider):
        def __init__(self, key, model='', *, transport=None): super().__init__(key, model, transport=httpx.MockTransport(handler))
    monkeypatch.setattr('app.providers.factory.GeminiScriptProvider', Patched)
    r = client.post(f'/api/channels/{ch["id"]}/style/suggest', json={'topic': 'Weltraum', 'audience': 'Jugendliche', 'feeling': 'gizemli'}).json()
    assert r['source'] == 'gemini' and r['style']['palette']['accent'] == '#00D1FF' and r['style']['subtitle']['font'] == 'montserrat'
    assert seen[0]['generationConfig']['responseMimeType'] == 'application/json'
    r = client.post(f'/api/channels/{ch["id"]}/style/suggest', json={'topic': 'x', 'audience': 'y', 'feeling': 'sakin'}).json()
    assert r['source'] == 'preset' and r['style']['palette'] == PRESETS['sakin']['palette']  # invalid AI answer never breaks the wizard
    # A suggestion is not saved until the owner presses Kaydet.
    assert client.get(f'/api/channels/{ch["id"]}').json()['style'] == DEFAULT_STYLE


def test_subtitle_style_from_kit_and_default_kit_keeps_old_look():
    cues = [{'start': 0, 'end': 1, 'text': 'Hallo'}]
    old, _, _ = ass.create(cues, [], 2)
    same, _, _ = ass.create(cues, [], 2, subtitle_style=DEFAULT_STYLE['subtitle'])
    assert same == old
    custom, _, _ = ass.create(cues, [], 2, subtitle_style={'font': 'bebas', 'color': '#FFD23F', 'outline': '#000000', 'position': 'top', 'size': 64})
    line = next(l for l in custom.splitlines() if l.startswith('Style: Subtitle,'))
    fields = line.split(',')
    assert fields[1] == 'Bebas Neue' and fields[2] == '64' and fields[3] == '&H003FD2FF' and fields[18] == '8'


def test_narration_preselects_the_channel_voice(client):
    ch = client.post('/api/channels', json={'name': 'Stimme', 'voice_provider': 'minimax', 'voice_id': 'minimax_voice1', 'voice_speed': 1.2}).json()
    p = client.post('/api/projects', json={'name': 'N', 'topic': 'Rom', 'channel_id': ch['id']}).json()
    settings = client.get(f'/api/projects/{p["id"]}/narration').json()['settings']
    assert settings['voice_id'] == 'minimax_voice1' and settings['voice_provider'] == 'minimax' and settings['speed'] == 1.2
    other = client.post('/api/projects', json={'name': 'M', 'topic': 'Rom'}).json()
    assert client.get(f'/api/projects/{other["id"]}/narration').json()['settings'].get('voice_id', '') != 'minimax_voice1'


def test_real_render_uses_the_kit_subtitle_font_colour_and_position(tmp_path):
    import shutil, subprocess
    from PIL import Image
    from test_rendering import NativeRenderClient, install_ready, url, await_job
    if not shutil.which('ffmpeg'): pytest.skip('FFmpeg absent')
    with NativeRenderClient(create_app(tmp_path / 'data'), headers=HEADERS) as c:
        st = install_ready(c.app); st.update(client=c, storage=tmp_path / 'data')
        ch = c.get('/api/channels').json()['channels'][0]
        c.put(f'/api/channels/{ch["id"]}', json={'style': {'subtitle': {'font': 'bebas', 'color': '#FFD23F', 'outline': '#000000', 'position': 'top', 'size': 72}}})
        r = c.post(url(st) + '/jobs', json={'encoder': 'cpu', 'editing_style': 'basic', 'subtitle_burned': True}); assert r.status_code == 202, r.text
        state = await_job(st); assert state['job']['status'] == 'completed', state['job']
        out = st['root'] / state['active']['metadata']['output_local_path']
        frame = tmp_path / 'f.png'
        subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-y', '-ss', '1.0', '-i', str(out), '-frames:v', '1', str(frame)], check=True)
        image = Image.open(frame).convert('RGB')
        yellow = lambda p: p[0] > 200 and p[1] > 170 and p[2] < 110
        top = sum(yellow(image.getpixel((x, y))) for x in range(0, 1920, 6) for y in range(20, 260, 6))
        bottom = sum(yellow(image.getpixel((x, y))) for x in range(0, 1920, 6) for y in range(820, 1060, 6))
        assert top > 50 and bottom < 5, (top, bottom)  # yellow kit subtitle at the top, not the old white bottom line
