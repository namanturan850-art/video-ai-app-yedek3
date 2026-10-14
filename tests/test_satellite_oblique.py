"""Ayarlar → Mapbox → Eğik görünüm: Mapbox Static Images API (one picture with
bearing/pitch per scene). No Mapbox account here (api.mapbox.com is not reachable
from the test machine): the pictures come from a fake provider that draws a
synthetic landscape through the same camera; the real API was not called."""
import io
import math
import subprocess

import httpx
import numpy as np
import pytest
from PIL import Image

import test_fast_media as F
from app.channels import DEFAULT_STYLE
from app.motion import relief, satellite_map
from app.providers import satellite
from app.providers.satellite import MapboxSatelliteProvider, SatelliteError

SAT = {**DEFAULT_STYLE, 'map_style': 'satellite', 'map_style_chosen': True}
URL = 'https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/{lon},{lat},{zoom},{bearing},{pitch}/{width}x{height}@2x'


def landscape(lon, lat, zoom, bearing, pitch, width, height, scale=2):
    """A synthetic tilted “satellite” picture: fields on a 0.08° grid, roads every 0.4°,
    drawn through the inverse of satellite_map.camera (so the marks must land on it)."""
    w, h = width * scale, height * scale
    world = 512 * 2 ** zoom
    cx, cy = (lon + 180) / 360 * world, satellite_map.merc_y(lat) * world
    b, p = math.radians(bearing), math.radians(pitch)
    distance = .5 / math.tan(satellite_map.FOV / 2) * height
    v, u = np.mgrid[0:h, 0:w] / scale
    sx, sy = u - width / 2, v - height / 2
    ry = sy * distance / (distance * math.cos(p) + sy * math.sin(p))
    rx = sx * (distance - ry * math.sin(p)) / distance
    dx, dy = rx * math.cos(b) - ry * math.sin(b), rx * math.sin(b) + ry * math.cos(b)
    plon = (cx + dx) / world * 360 - 180
    plat = np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * (cy + dy) / world))))
    cell = (np.floor(plon / .08) * 7 + np.floor(plat / .08) * 13).astype(int) % 3
    colours = np.array([[58, 92, 48], [104, 110, 64], [128, 104, 76]])
    image = colours[cell]
    road = (np.abs(plon / .4 - np.round(plon / .4)) < .02) | (np.abs(plat / .4 - np.round(plat / .4)) < .02)
    image[road] = [190, 186, 176]
    haze = np.clip((v / height) * .35 + .65, 0, 1)[..., None]  # far away is paler
    image = image * haze + 200 * (1 - haze)
    out = io.BytesIO(); Image.fromarray(image.astype('uint8')).save(out, 'JPEG', quality=88); return out.getvalue()


class FakeMapbox(satellite.SatelliteProvider):
    attribution = '© Mapbox'

    def __init__(self, static_error=None):
        self.static_error, self.calls = static_error, []

    def static(self, *args):
        self.calls.append(args)
        if self.static_error: raise self.static_error
        return landscape(*args)

    def tile(self, z, x, y):
        out = io.BytesIO(); Image.new('RGB', (512, 512), (40, 90, 60)).save(out, 'JPEG'); return out.getvalue()


def render(kind, value, tmp_path, monkeypatch, *, oblique=True, provider=None, at=3.5):
    from app.motion.raster import render as raster
    from app.motion.templates import build
    from app.motion.templates_extra import parse
    provider = provider or FakeMapbox()
    monkeypatch.setattr(satellite, 'FACTORY', lambda: provider)
    monkeypatch.setattr(satellite, 'OBLIQUE', lambda: oblique)
    relief.LAST_WARNING = ''
    scene = build(parse(kind, value), SAT, 4., 2., 'fr')
    out = tmp_path / 'clip.mp4'
    raster(scene, out, 'ffmpeg')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(at), '-i', str(out), '-frames:v', '1', str(tmp_path / 'f.png')], check=True)
    return scene, np.asarray(Image.open(tmp_path / 'f.png').convert('RGB'), dtype=np.int16), provider


def test_static_request_shape_and_errors():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=landscape(2.35, 48.86, 6, 0, 0, 40, 30, 1), headers={'Content-Type': 'image/jpeg'})
    p = MapboxSatelliteProvider('pk.test-key-123', 'https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}@2x.jpg90', static_url=URL, transport=httpx.MockTransport(handler))
    assert p.static(2.35, 48.86, 6.5, 290.4, 40, 1280, 720).startswith(b'\xff\xd8')
    assert seen[0].url.path == '/styles/v1/mapbox/satellite-v9/static/2.35000,48.86000,6.50,290.4,40.0/1280x720@2x'
    assert seen[0].url.params['access_token'] == 'pk.test-key-123'
    p.static(0, 0, 30, -20, 80, 5000, 900)  # limits kept: zoom ≤ 22, pitch ≤ 60, width ≤ 1280
    assert seen[1].url.path.endswith('/0.00000,0.00000,22.00,340.0,60.0/1280x900@2x')
    bad = MapboxSatelliteProvider('pk.test-key-123', 'x', static_url=URL, transport=httpx.MockTransport(lambda r: httpx.Response(422)))
    with pytest.raises(SatelliteError) as error: bad.static(2, 48, 6, 0, 40, 1280, 720)
    assert '422' in str(error.value) and 'Eğik görünüm' in str(error.value)


def test_camera_puts_the_destination_ahead():
    points = [(2.35, 48.86), (-1.674, 48.111)]
    lon, lat, zoom, bearing, pitch = satellite_map.oblique_view(points, route=True)
    assert 240 < bearing < 280 and pitch == 40  # Paris → Rennes heads west
    project = satellite_map.camera(lon, lat, zoom, bearing, pitch, 1280, 720)
    (x0, y0), (x1, y1) = project(*points[0]), project(*points[1])
    assert y1 < y0 and abs(x1 - x0) < 60  # Rennes straight ahead, “into” the picture
    assert all(.15 * 1280 < x < .85 * 1280 and .15 * 720 < y < .85 * 720 for x, y in ((x0, y0), (x1, y1)))
    flat = satellite_map.camera(2.35, 48.86, 8, 0, 0, 1280, 720)
    assert flat(2.35, 48.86) == (640, 360) and flat(3, 48.86)[0] > 640 and flat(2.35, 49.2)[1] < 360


def test_ok_marker_on_the_oblique_view(tmp_path, monkeypatch):
    scene, frame, provider = render('arrow', 'Paris > Rennes | 350 km', tmp_path, monkeypatch)
    assert next(e for e in scene['elements'] if e['type'] == 'relief')['props']['view'] == 'oblique'
    assert relief.LAST_WARNING == '' and len(provider.calls) == 1  # one request for the whole scene
    yellow = (frame[..., 0] > 200) & (frame[..., 1] > 170) & (frame[..., 2] < 90)
    assert yellow.mean() > .002  # the yellow [OK] line
    assert (frame.sum(axis=-1) < 140).mean() < .2  # the picture, not the dark drawn map
    white = (frame > 230).all(axis=-1)
    assert white[30:140, 40:500].mean() > .02  # badge


def test_oblique_off_gives_the_flat_view(tmp_path, monkeypatch):
    scene, frame, provider = render('arrow', 'Paris > Rennes', tmp_path, monkeypatch, oblique=False)
    assert 'view' not in next(e for e in scene['elements'] if e['type'] == 'relief')['props'] and provider.calls == []
    assert (abs(frame[300:500, 300:700] - np.array([40, 90, 60])).max(axis=-1) < 30).mean() > .3  # flat tiles


def test_failed_static_request_falls_back_to_the_flat_view_with_a_turkish_reason(tmp_path, monkeypatch):
    error = SatelliteError('key_rejected', satellite.MESSAGES['key_rejected'])
    scene, frame, provider = render('route', 'Paris > Rennes > Brest', tmp_path, monkeypatch, provider=FakeMapbox(static_error=error))
    assert relief.LAST_WARNING.startswith('Eğik görünüm alınamadı (Mapbox anahtarı kabul edilmedi (401/403))')
    assert 'düz uydu görünümü' in relief.LAST_WARNING
    assert (abs(frame[300:500, 300:700] - np.array([40, 90, 60])).max(axis=-1) < 30).mean() > .3
    relief.LAST_WARNING = ''


def test_harita_marker_uses_the_satellite_style(monkeypatch):
    from app.motion.templates import build
    monkeypatch.setattr(satellite, 'OBLIQUE', lambda: True)
    spec = {'template': 'map', 'data': {'place': 'Rennes', 'label': '', 'lat': 48.111, 'lon': -1.674}, 'emphasis': ''}
    element = next(e for e in build(spec, SAT, 4., 2., 'fr')['elements'] if e['type'] == 'relief')
    assert element['props']['theme'] == 'satellite' and element['props']['view'] == 'oblique'
    assert relief.plan(element['props']['spec'])['unit']['name'] == 'Rennes'
    assert not any(e['type'] == 'relief' for e in build(spec, DEFAULT_STYLE, 4., 2., 'fr')['elements'])  # other styles: unchanged


def test_settings_checkbox(tmp_path, monkeypatch):
    client, pid, world, fake = F.make(tmp_path, monkeypatch)
    try:
        s = client.app.state.settings
        assert s.mapbox_config()['oblique'] is True and s.mapbox_config()['static_url'] == URL
        assert satellite.oblique() is True
        assert client.put('/api/settings/mapbox', json={'oblique': False}, headers=F.SETTINGS).status_code == 200
        assert s.mapbox_config()['oblique'] is False and satellite.oblique() is False
        r = client.put('/api/settings/mapbox', json={'static_url': 'https://example.com/{lon}'}, headers=F.SETTINGS)
        assert r.status_code >= 400
        assert 'Eğik görünüm' in client.get('/static/settings.js').text
    finally:
        client.__exit__(None, None, None)


def mapbox_like(seen=None, static_status=200):
    """A MapboxSatelliteProvider whose HTTP answers come from landscape() / a flat tile."""
    def handler(request):
        if seen is not None: seen.append(request)
        if '/static/' in request.url.path:
            if static_status != 200: return httpx.Response(static_status)
            a = request.url.path.split('/static/')[1].split('/')
            lon, lat, z, b, p = map(float, a[0].split(',')); w, h = a[1].split('@')[0].split('x')
            return httpx.Response(200, content=landscape(lon, lat, z, b, p, int(w) // 4, int(h) // 4, 1))
        out = io.BytesIO(); Image.new('RGB', (512, 512), (40, 90, 60)).save(out, 'JPEG'); return httpx.Response(200, content=out.getvalue())
    return httpx.MockTransport(handler)


def test_render_diagnostics_name_the_view_and_the_request_without_the_key(tmp_path, monkeypatch):
    seen = []
    provider = MapboxSatelliteProvider('pk.secret-key-98765', 'https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}@2x.jpg90', static_url=URL, transport=mapbox_like(seen))
    render('arrow', 'Paris > Rennes | 350 km', tmp_path, monkeypatch, provider=provider)
    static = [r for r in seen if '/static/' in r.url.path]
    assert len(static) == 1 and static[0].url.path.endswith(',40.0/1280x720@2x')  # pitch 40 really sent
    bearing = float(static[0].url.path.split('/static/')[1].split(',')[3])
    assert 240 < bearing < 280  # the route's direction (Paris → Rennes: west)
    assert relief.LAST_INFO.startswith('Harita (Paris → Rennes): eğik görünüm (eğim 40°')
    assert '/styles/v1/mapbox/satellite-v9/static/' in relief.LAST_INFO and 'access_token=pk.***8765' in relief.LAST_INFO
    assert 'secret-key' not in relief.LAST_INFO
    render('arrow', 'Paris > Rennes', tmp_path, monkeypatch, provider=provider, oblique=False)
    assert 'düz uydu görünümü' in relief.LAST_INFO and '“Eğik görünüm”' in relief.LAST_INFO and 'kapalı' in relief.LAST_INFO
    failing = MapboxSatelliteProvider('pk.secret-key-98765', 'https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}@2x.jpg90', static_url=URL, transport=mapbox_like(static_status=403))
    render('arrow', 'Paris > Rennes', tmp_path, monkeypatch, provider=failing)
    assert 'eğik görünüm alınamadı' in relief.LAST_INFO and '/static/' in relief.LAST_INFO and 'secret-key' not in relief.LAST_INFO
    relief.LAST_WARNING = relief.LAST_INFO = ''


def test_connection_button_also_checks_the_oblique_request():
    from app.providers.satellite import mapbox_check
    tiles = 'https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}@2x.jpg90'
    config = {'api_key': 'pk.secret-key-98765', 'tile_url': tiles, 'static_url': URL, 'oblique': True}
    ok = mapbox_check(config, transport=mapbox_like())
    assert ok['status'] == 'Hazır' and 'Eğik görünüm' in ok['message'] and ',45.0/300x200@2x?access_token=pk.***8765' in ok['request']
    bad = mapbox_check(config, transport=mapbox_like(static_status=403))
    assert bad['status'] == 'Hata' and 'eğik görünüm çalışmıyor' in bad['message'] and 'styles:tiles' in bad['message']
    assert 'secret-key' not in str(bad)
    off = mapbox_check({**config, 'oblique': False}, transport=mapbox_like(static_status=403))
    assert off['status'] == 'Hazır' and 'Eğik görünüm kapalı' in off['message']
