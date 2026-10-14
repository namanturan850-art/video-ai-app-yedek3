"""Harita stili → Uydu görüntüsü reaches the map templates ([OK], [ROTA]) in the
media job and at render time. No Mapbox account here: tiles come from a fake
HTTP transport (a synthetic textured picture); the real API was not called."""
import io
import subprocess

import httpx
import numpy as np
from PIL import Image

import test_fast_media as F
import test_media_director_topics as T
from app.channels import DEFAULT_STYLE
from app.motion import relief
from app.providers import satellite
from app.providers.satellite import MapboxSatelliteProvider

SAT = {**DEFAULT_STYLE, 'map_style': 'satellite', 'map_style_chosen': True}
FR = """# La Bretagne

De Paris à Rennes, la route traverse toute la plaine. [OK: Paris > Rennes | 350 km]
Le voyage continuait ensuite jusqu'à la mer. [ROTA: Paris > Rennes > Brest]
Les pêcheurs bretons partaient pour des mois en mer.
"""


def textured_tile(z, x, y):
    """A synthetic “satellite” tile: green/brown fields with noise (not a real photo)."""
    rng = np.random.default_rng(z * 1_000_003 + x * 1009 + y)
    field = rng.integers(0, 3, (16, 16))[..., None]
    colours = np.array([[58, 92, 48], [96, 104, 60], [120, 100, 72]])
    image = colours[field[..., 0]].repeat(32, 0).repeat(32, 1) + rng.integers(-14, 14, (512, 512, 3))
    out = io.BytesIO(); Image.fromarray(np.clip(image, 0, 255).astype('uint8')).save(out, 'JPEG', quality=85); return out.getvalue()


def fake_mapbox(monkeypatch):
    def handler(request):
        z, x, y = request.url.path.split('/')[-3:]
        return httpx.Response(200, content=textured_tile(int(z), int(x), int(y.split('@')[0])), headers={'Content-Type': 'image/jpeg'})
    monkeypatch.setattr(satellite, 'FACTORY', lambda: MapboxSatelliteProvider(
        'pk.test-key-123', 'https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}@2x.jpg90', transport=httpx.MockTransport(handler)))


def frame_of(path, at, out):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(at), '-i', str(path), '-frames:v', '1', str(out)], check=True)
    return np.asarray(Image.open(out).convert('RGB'), dtype=np.int16)


def satellite_look(frame):
    yellow = ((frame[..., 0] > 200) & (frame[..., 1] > 170) & (frame[..., 2] < 90)).mean()
    green = ((frame[..., 1] > frame[..., 2] + 15) & (frame[..., 1] > 60)).mean()
    return yellow, green


def test_route_and_arrow_use_satellite_when_chosen():
    from app.motion.templates import build
    from app.motion.templates_extra import parse
    for kind, value in (('arrow', 'Paris > Rennes | 350 km'), ('route', 'Paris > Rennes > Brest')):
        spec = parse(kind, value)
        relief_el = [e for e in build(spec, SAT, 4., 2., 'fr')['elements'] if e['type'] == 'relief']
        assert relief_el and relief_el[0]['props']['theme'] == 'satellite' and relief_el[0]['props']['lang'] == 'fr'
        dark = build(spec, DEFAULT_STYLE, 4., 2., 'fr')['elements']
        assert not any(e['props'].get('theme') == 'satellite' for e in dark)  # not chosen: the dark default
    info = relief.plan(relief_el[0]['props']['spec'])
    assert [p[2] for p in info['arrow']] == ['Paris', 'Rennes', 'Brest']
    assert info['arrow'][2][0] < -4  # Brest in France (west of Rennes), not Brest in Belarus


def test_look_preset_keeps_a_chosen_map_style(tmp_path, monkeypatch):
    client, pid, world, fake = F.make(tmp_path, monkeypatch, FR, language='fr')
    try:
        client.put('/api/settings/mapbox', json={'api_key': 'pk.synthetic-mapbox-key-4444'}, headers=F.SETTINGS)
        assert client.put(f'/api/projects/{pid}/look', json={'map_style': 'satellite'}, headers=F.HEADERS).json()['map_style'] == 'satellite'
        r = client.put(f'/api/projects/{pid}/look', json={'look': 'koyu_harita'}, headers=F.HEADERS)
        assert r.json()['map_style'] == 'satellite'  # picking “Video görünümü” no longer resets Harita stili
    finally:
        client.__exit__(None, None, None)


def test_french_ok_marker_end_to_end_on_satellite(tmp_path, monkeypatch):
    client, pid, world, fake = F.make(tmp_path, monkeypatch, FR, language='fr', fast=False)
    try:
        fake_mapbox(monkeypatch)  # after start-up: the app sets the real Mapbox factory
        client.put('/api/settings/mapbox', json={'api_key': 'pk.synthetic-mapbox-key-4444'}, headers=F.HEADERS | F.SETTINGS)
        assert client.put(f'/api/projects/{pid}/look', json={'map_style': 'satellite'}, headers=F.HEADERS).status_code == 200
        client.app.state.stock.clip_scorer = F.clip_fake(world, [])
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed', view['job']
        assert not (view['job'].get('progress') or {}).get('marker_warnings')
        maps = [s for s in view['slots'] if ((s['selected_media'] or {}).get('source_metadata') or {}).get('motion', {}).get('template') in ('relief', 'route')]
        assert {s['selected_media']['source_metadata']['motion']['template'] for s in maps} == {'relief', 'route'}
        folder = client.app.state.projects._path(pid)
        for slot in maps:
            path = folder / slot['selected_media']['local_path']
            assert '-fallback-' not in path.name
            yellow, green = satellite_look(frame_of(path, 2.5, tmp_path / 'f.png'))
            assert yellow > .001 and green > .3  # the yellow line on the (fake) satellite picture, not the dark vector map
        # render time: the kit the render job uses (channel style) still says satellite
        from app.motion.templates import build
        kit = client.app.state.channels.for_project(pid)['style']
        spec = maps[0]['selected_media']['source_metadata']['motion']
        assert any(e['props'].get('theme') == 'satellite' for e in build(spec, kit, 4., 2., 'fr')['elements'])
    finally:
        client.__exit__(None, None, None)
