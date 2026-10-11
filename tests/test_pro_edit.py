"""Professional edit pass: transition styles + whoosh, graphic text overlays,
one-click video look, Kanallar hidden from the menu. No network."""
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.channels import PRESETS
from app.main import create_app
from app.rendering import ass, smart_edit, timeline
from app.rendering.engine import XFADE_STYLES
from app.rendering.service import RenderService
from test_scripts import HEADERS
from test_smart_edit import owner_shape


def test_motion_scenes_slide_in_and_out_and_other_cuts_vary():
    h, p = owner_shape(); t = timeline.build(h, p)
    motion = [s['slot_id'] for s in t['slots'] if s['scene_id'] == 'scene-14']
    plan = smart_edit.build(t, h, 'balanced', 'src', media_details={sid: {'motion': True} for sid in motion})
    items = plan['slots']; i = next(n for n, s in enumerate(items) if s['slot_id'] == motion[0])
    assert items[i - 1]['transition_out'] == 'crossfade' and items[i - 1]['transition_style'] == 'smoothleft'
    last = next(n for n, s in enumerate(items) if s['slot_id'] == motion[-1])
    assert items[last]['transition_out'] == 'crossfade' and items[last]['transition_style'] == 'smoothright'
    styles = {s.get('transition_style') for s in items if s['transition_out'] == 'crossfade'}
    assert {'fade', 'zoomin'} <= styles and styles <= set(XFADE_STYLES)
    assert plan == smart_edit.build(t, h, 'balanced', 'src', media_details={sid: {'motion': True} for sid in motion})  # deterministic
    basic = smart_edit.build(t, h, 'basic', 'src', media_details={sid: {'motion': True} for sid in motion})
    assert not any('transition_style' in s for s in basic['slots'])  # “Temel” stays plain


def test_whoosh_under_styled_transitions_only():
    plan = {'slots': [{'end': 5, 'transition_out': 'crossfade', 'transition_duration': .4, 'transition_style': 'zoomin'},
                      {'end': 9, 'transition_out': 'crossfade', 'transition_duration': .4, 'transition_style': 'fade'},
                      {'end': 14, 'transition_out': 'hard_cut', 'transition_duration': 0}]}
    out = RenderService._transition_sfx(None, plan, {'events': [], 'volume': .18}, {'sfx': {}}, {'audio_duration': 20})
    assert [(e['t'], e['sound']) for e in out['events']] == [(4.45, 'whoosh')] and Path(out['events'][0]['path']).is_file()
    assert RenderService._transition_sfx(None, plan, {'events': []}, {'sfx': {'whoosh': 'none'}}, {})['events'] == []


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg absent')
def test_every_transition_style_is_a_real_ffmpeg_xfade(tmp_path):
    for style in XFADE_STYLES:
        r = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=red:s=320x180:d=1:r=30', '-f', 'lavfi', '-i', 'color=blue:s=320x180:d=1:r=30',
                            '-filter_complex', f'[0][1]xfade=transition={style}:duration=0.4:offset=0.3', '-f', 'null', '-'], capture_output=True, text=True)
        assert r.returncode == 0, (style, r.stderr[-300:])


def test_emphasis_texts_become_graphics_in_the_look_colours():
    g = {**{k: PRESETS['gizemli']['palette'][k] for k in ('background', 'accent', 'primary')}, 'font': 'Oswald'}
    items = [{'start': 1, 'end': 3, 'text': '1945: Das letzte Signal', 'style': 'upper_left'}, {'start': 4, 'end': 6, 'text': 'Niemand kam {zurück}', 'style': 'center'}]
    content, warnings, has = ass.create([], [], 8, subtitles=False, overlays=True, editing_style='adaptive', emphasis=items, graphic_style=g)
    events = [l for l in content.splitlines() if l.startswith('Dialogue:')]
    assert has and not warnings and len(events) == 6 and 'Style: Graphic,' in content
    accent = ass.ass_colour(g['accent'])[4:]
    assert sum('\\p1' in e and f'\\1c&H{accent}&' in e for e in events) == 2  # one growing accent bar per text
    assert sum('\\fnOswald' in e for e in events) == 2 and r'Niemand kam \{zurück\}' in content  # text stays escaped
    plain, _, _ = ass.create([], [], 8, subtitles=False, overlays=True, editing_style='adaptive', emphasis=items)
    assert 'Graphic' not in plain and 'EmphasisLeft' in plain


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg absent')
def test_graphics_burn_with_libass(tmp_path):
    g = {**{k: PRESETS['enerjik']['palette'][k] for k in ('background', 'accent', 'primary')}, 'font': 'Bebas Neue'}
    content, _, _ = ass.create([], [], 3, subtitles=False, overlays=True, editing_style='adaptive', emphasis=[{'start': .2, 'end': 2.8, 'text': 'Drei Fakten', 'style': 'center'}], graphic_style=g)
    (tmp_path / 'g.ass').write_text(content, encoding='utf-8'); (tmp_path / 'fonts').mkdir()
    shutil.copyfile(Path('app/static/fonts/BebasNeue-Regular.ttf'), tmp_path / 'fonts' / 'BebasNeue-Regular.ttf')
    out = tmp_path / 'f.png'
    r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=0x808080:s=1920x1080:d=3:r=30', '-vf', 'ass=filename=g.ass:fontsdir=fonts',
                        '-ss', '1.5', '-frames:v', '1', 'f.png'], cwd=tmp_path, capture_output=True, text=True)
    if r.returncode and 'ass' in r.stderr: pytest.skip('FFmpeg without libass')
    from PIL import Image
    img = Image.open(out).convert('RGB')
    accent = tuple(int(PRESETS['enerjik']['palette']['accent'][i:i + 2], 16) for i in (1, 3, 5))
    assert any(sum(abs(a - b) for a, b in zip(img.getpixel((x, y)), accent)) < 30 for x in range(600, 1320, 8) for y in range(150, 330, 2))  # accent bar drawn


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        yield client


def test_one_click_look_and_menu(client):
    pid = client.post('/api/projects', json={'name': 'P', 'topic': 'Rom'}).json()['id']
    view = client.get(f'/api/projects/{pid}/look').json()
    assert view['look'] == '' and len(view['looks']) == 6
    r = client.put(f'/api/projects/{pid}/look', json={'look': 'gizemli'})
    assert r.status_code == 200 and r.json()['look'] == 'gizemli'
    style = client.app.state.channels.for_project(pid)['style']
    assert style['palette'] == PRESETS['gizemli']['palette'] and style['heading_font'] == 'oswald'
    assert client.put(f'/api/projects/{pid}/look', json={'look': 'x'}).status_code == 422
    assert client.put(f'/api/projects/{pid}/look', json={'look': 'gizemli'}, headers={'X-AI-Video-Studio': ''}).status_code == 403
    home = client.get('/').text
    assert 'href="/channels"' not in home  # Kanallar is no longer in the menu (data is kept)
    assert client.get('/api/channels').status_code == 200
