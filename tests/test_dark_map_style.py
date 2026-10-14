"""“Koyu harita belgeseli” stili: [SIRA] rozeti, koyu düz harita (+ [KARŞILAŞTIR]
bindirme, rakam kutusu), [ŞERİT] iki satırlı alt şerit, kelime vurgusu, [ARŞİV]."""
import subprocess

import numpy as np
from PIL import Image

import test_fast_media as F
import test_media_director_topics as T
from app.channels import DEFAULT_STYLE, PRESETS

KIT = {**DEFAULT_STYLE, **{k: v for k, v in PRESETS['koyu_harita'].items() if k != 'word_highlight'}}

FR = """# La France cachée

La France cache quelque chose dont personne ne parle. [SIRA: 23/30 | La France cachée]
La Bretagne est presque aussi grande que la Belgique. [KARŞILAŞTIR: Bretagne | Belgique]
De Paris à New York, il y a plus de six mille kilomètres. [OK: Paris > New York | 6.640 mil]
Les pêcheurs bretons partaient pour des mois en mer. [ŞERİT: Bretagne, 1910 | Les pêcheurs partaient pour des mois]
Une vieille photo montre le port de Brest. [ARŞİV: old harbor photo]
En Guyane, la forêt couvre presque tout le territoire. [BÖLGE: Guyane | 83.534 km²]
"""

TR = """# Gizli Fransa

Fransa'nın kimsenin bilmediği bir yüzü var. [SIRA: 5/12 | Gizli Fransa]
Bretanya neredeyse Belçika kadar büyüktür. [KARŞILAŞTIR: Bretagne | Belgique]
Balıkçılar aylarca denizde kalırdı. [ŞERİT: Bretanya, 1910 | Balıkçılar aylarca denizdeydi]
Guyana'da orman neredeyse her yeri kaplar. [BÖLGE: Guyane]
"""


def render_frame(spec, tmp_path, at=3.9, duration=4.):
    from app.motion.raster import render
    from app.motion.templates import build
    out = tmp_path / 'clip.mp4'
    render(build(spec, KIT, duration, 2., 'fr'), out, 'ffmpeg')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(at), '-i', str(out), '-frames:v', '1', str(tmp_path / 'f.png')], check=True)
    return np.asarray(Image.open(tmp_path / 'f.png').convert('RGB'), dtype=np.int16)


def test_dark_map_compare_overlay_and_number_box(tmp_path):
    from app.motion.templates_extra import parse, relief_marker
    spec = relief_marker('compare', 'Bretagne | Belgique')
    assert spec['data']['mode'] == 'compare'
    frame = render_frame(spec, tmp_path)
    blue = (frame[..., 2] - frame[..., 0] > 90) & (frame[..., 2] > 150)
    orange = (frame[..., 0] - frame[..., 2] > 60) & (frame[..., 0] > 140)
    navy = (frame.sum(axis=-1) < 140)
    assert blue.mean() > .005 and orange.mean() > .01 and navy.mean() > .3  # blue area, orange overlay, dark navy map
    from app.motion.relief import plan
    assert plan(spec)['figure'] in ('1,1×', '1,2×')  # Bretagne ≈ 27 000 km², Belgique ≈ 30 500 km²
    arrow = parse('arrow', 'Paris > New York | 6.640 mil')
    assert arrow['data']['figure'] == '6.640 mil'
    frame = render_frame(arrow, tmp_path)
    assert (frame[60:180, 1500:1880] > 235).all(axis=-1).mean() > .02  # white number text in the top-right box


def test_archive_photo_frame(tmp_path):
    from app.motion.templates_extra import parse
    photo = tmp_path / 'photo.jpg'
    Image.new('RGB', (1200, 800), (150, 110, 70)).save(photo)
    spec = parse('archive', 'old harbor photo'); spec['data']['image_path'] = str(photo)
    frame = render_frame(spec, tmp_path, at=1.)
    white = (frame > 235).all(axis=-1)
    assert white.mean() > .02  # the white frame
    assert (frame[540, 960] - np.array([150, 110, 70])).__abs__().max() < 25  # the photo in the middle


def test_badge_band_and_word_highlight_in_subtitles():
    from app.rendering import ass
    from app.rendering.smart_edit import badges, lower_thirds
    t = {'scenes': [{'scene_id': 's1', 'start': 0., 'end': 8.}], 'editing_scenes': [{'scene_id': 's1', 'owner_hints': [{'type': 'sequence', 'value': '23/30 | La France cachée'}]}],
         'slots': [{'scene_id': 's1', 'slot_id': 'a', 'start': 0., 'end': 8., 'duration': 8., 'band': {'top': 'Bretagne, 1910', 'bottom': 'Les pêcheurs partaient'}}]}
    badge = badges(t)[0]
    assert badge['text'] == '23/30 · LA FRANCE CACHÉE' and badge['fraction'] == round(23 / 30, 4) and badge['end'] == 8.
    band = lower_thirds(t)[0]
    assert band['style'] == 'band2' and band['top'] == 'Bretagne, 1910' and band['end'] - band['start'] <= 6
    style = {**DEFAULT_STYLE['subtitle'], 'word_highlight': True}
    content, _, _ = ass.create([{'start': 0., 'end': 3., 'text': 'Les pêcheurs partaient en mer'}], [], 10., editing_style='adaptive',
                               emphasis=[badge, band], subtitle_style=style, graphic_style={'background': '#0B1426', 'accent': '#3D9BFF', 'primary': '#FFFFFF', 'font': 'Montserrat'})
    assert content.count(',Subtitle,') == 5 and '\\3c&HFF9B3D&\\bord10' in content  # one line per word, the word boxed in the accent colour
    assert '23/30 · LA FRANCE CACHÉE' in content and 'BRETAGNE, 1910' in content and '\\t(400,401,\\alpha&H00&)' in content  # typewriter
    plain, _, _ = ass.create([{'start': 0., 'end': 3., 'text': 'Les pêcheurs partaient en mer'}], [], 10.)
    assert plain.count(',Subtitle,') == 1  # off by default


def test_look_switches_map_style_and_word_highlight(tmp_path, monkeypatch):
    client, pid, world, fake = F.make(tmp_path, monkeypatch, FR, language='fr')
    try:
        r = client.put(f'/api/projects/{pid}/look', json={'look': 'koyu_harita'}, headers=F.HEADERS)
        assert r.status_code == 200 and r.json()['map_style'] == 'dark' and r.json()['word_highlight'] is True
        r = client.put(f'/api/projects/{pid}/look', json={'map_style': 'relief', 'word_highlight': False}, headers=F.HEADERS)
        assert r.json()['map_style'] == 'relief' and r.json()['word_highlight'] is False
        assert 'Harita stili' in client.get('/static/render.js').text
    finally:
        client.__exit__(None, None, None)


def run_text(tmp_path, monkeypatch, text, language):
    client, pid, world, fake = F.make(tmp_path, monkeypatch, text, language=language)
    try:
        world.items.insert(0, {'id': 8_500_001, 'tags': 'old harbor photo port', 'kind': 'image', 'portrait': False, 'duration': 8})
        colour = client.app.state.stock.fetch_thumbnail  # the archive photo is black and white (the topic is ancient: only old-looking photos fit)
        client.app.state.stock.fetch_thumbnail = lambda url: F.jpeg((120, 120, 120)) if ('8500001' in url or '9400001' in url) else colour(url)
        client.put(f'/api/projects/{pid}/look', json={'look': 'koyu_harita'}, headers=F.HEADERS)
        plan = client.get(f'/api/projects/{pid}/production').json()['plan']
        hints = {h['type'] for b in plan['blocks'] for h in b.get('owner_hints') or []}
        client.app.state.stock.clip_scorer = F.clip_fake(world, [])
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed' and view['media_summary']['missing'] == 0, view['job']
        motions = [((s['selected_media'] or {}).get('source_metadata') or {}).get('motion') or {} for s in view['slots']]
        return hints, motions, view
    finally:
        client.__exit__(None, None, None)


def test_french_text_end_to_end(tmp_path, monkeypatch):
    hints, motions, view = run_text(tmp_path, monkeypatch, FR, 'fr')
    assert {'sequence', 'compare', 'arrow', 'band', 'archive', 'region'} <= hints
    modes = {m['data'].get('mode') for m in motions if m.get('template') == 'relief'}
    assert {'compare', 'arrow', 'region'} <= modes
    assert any(m.get('template') == 'archive' and m['data'].get('image') for m in motions), [s.get('message') for s in view['slots']] + [view['job']['progress'].get('marker_warnings')]
    assert any(s.get('band', {}).get('top') == 'Bretagne, 1910' for s in view['slots'])
    assert not {'intro', 'outro'} & {m.get('template') for m in motions}  # no opening / closing card by default


def test_channel_moments_are_off_by_default(tmp_path, monkeypatch):
    client, pid, world, fake = F.make(tmp_path, monkeypatch, FR, language='fr')
    try:
        general = client.get('/api/settings', headers=F.SETTINGS).json()['general']
        assert general['intro_card'] is False and general['outro_card'] is False and general['end_screen'] is False
        assert client.app.state.settings.moments() == {'intro_card': False, 'outro_card': False, 'end_screen': False}
        assert client.get(f'/api/projects/{pid}/look', headers=F.HEADERS).json()['map_style'] == 'dark'  # the dark map is the default
    finally:
        client.__exit__(None, None, None)


def test_turkish_text_end_to_end(tmp_path, monkeypatch):
    hints, motions, view = run_text(tmp_path, monkeypatch, TR, 'tr')
    assert {'sequence', 'compare', 'band', 'region'} <= hints
    assert {'compare', 'region'} <= {m['data'].get('mode') for m in motions if m.get('template') == 'relief'}
    assert any(s.get('band', {}).get('bottom') == 'Balıkçılar aylarca denizdeydi' for s in view['slots'])


def test_archive_period_needs_an_old_looking_photo():
    from app.stock.director_media import MediaDirector
    d = MediaDirector.__new__(MediaDirector)
    d.setting = None
    assert d.archive_period({'label': 'port de Brest', 'source': 'port de Brest, 1910'}, {'narration_text': ''}) == '1910'
    assert d.archive_period({'label': 'harbor', 'source': 'harbor'}, {'narration_text': 'Le port aujourd\'hui.'}) == ''
    d.frame_urls = lambda media: ['u']
    import base64
    block = lambda colour: {'source': {'data': base64.b64encode(F.jpeg(colour)).decode()}}
    d.thumbnail = lambda url, provider: block((128, 128, 128))
    assert d.looks_old({'provider': 'pixabay', 'description': 'harbor'})
    d.thumbnail = lambda url, provider: block((30, 140, 220))
    assert not d.looks_old({'provider': 'pixabay', 'description': 'harbor'})  # a colourful modern photo never passes as archive
