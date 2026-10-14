"""Harita stili → Uydu görüntüsü (SatelliteProvider / Mapbox). No Mapbox account
here: tiles come from a fake HTTP transport; the real API was not called."""
import io
import subprocess

import httpx
import numpy as np
import pytest
from PIL import Image

import test_fast_media as F
from app.channels import DEFAULT_STYLE
from app.motion import relief
from app.providers import satellite
from app.providers.satellite import MapboxSatelliteProvider, SatelliteError

SAT = {**DEFAULT_STYLE, 'map_style': 'satellite', 'map_style_chosen': True}


def tile_bytes(colour=(40, 90, 60)):
    out = io.BytesIO(); Image.new('RGB', (512, 512), colour).save(out, 'JPEG'); return out.getvalue()


def fake(status=200, body=None, seen=None):
    def handler(request):
        if seen is not None: seen.append(request)
        return httpx.Response(status, content=body if body is not None else tile_bytes(), headers={'Content-Type': 'image/jpeg'})
    return httpx.MockTransport(handler)


def render(spec_kind, value, tmp_path, at=1.5):
    from app.motion.raster import render as raster
    from app.motion.templates import build
    from app.motion.templates_extra import parse
    out = tmp_path / 'clip.mp4'
    raster(build(parse(spec_kind, value), SAT, 2., 1., 'fr'), out, 'ffmpeg')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(at), '-i', str(out), '-frames:v', '1', str(tmp_path / 'f.png')], check=True)
    return np.asarray(Image.open(tmp_path / 'f.png').convert('RGB'), dtype=np.int16)


def test_provider_errors_are_turkish():
    with pytest.raises(SatelliteError) as error: MapboxSatelliteProvider('', 'https://api.mapbox.com/v4/x/{z}/{x}/{y}.jpg')
    assert 'Mapbox API anahtarı girilmeli (Ayarlar)' in str(error.value)
    for status, word in ((401, 'kabul edilmedi'), (429, 'sınırına'), (404, 'bulamadı'), (500, 'sunucusu')):
        p = MapboxSatelliteProvider('pk.test-key-123', 'https://api.mapbox.com/v4/x/{z}/{x}/{y}.jpg', transport=fake(status))
        with pytest.raises(SatelliteError) as error: p.tile(3, 1, 2)
        assert word in str(error.value)
    with pytest.raises(SatelliteError): MapboxSatelliteProvider('pk.test-key-123', 'https://api.mapbox.com/v4/x/{z}/{x}/{y}.jpg', transport=fake(body=b'<html>')).tile(1, 0, 0)


def test_key_goes_as_query_parameter_and_tiles_are_cached_without_it(tmp_path):
    seen = []
    p = MapboxSatelliteProvider('pk.test-key-123', 'https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}@2x.jpg90', cache=tmp_path, transport=fake(seen=seen))
    assert p.tile(5, 15, 11).startswith(b'\xff\xd8') and p.tile(5, 15, 11)
    assert len(seen) == 1 and seen[0].url.path == '/v4/mapbox.satellite/5/15/11@2x.jpg90' and seen[0].url.params['access_token'] == 'pk.test-key-123'
    assert not any('pk.test' in f.name for f in tmp_path.iterdir())


def test_satellite_map_with_marks(tmp_path, monkeypatch):
    monkeypatch.setattr(satellite, 'FACTORY', lambda: MapboxSatelliteProvider('pk.test-key-123', 'https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}@2x.jpg90', transport=fake()))
    frame = render('region', 'Bretagne | 27.208 km²', tmp_path)
    assert relief.LAST_WARNING == ''
    green = (abs(frame[150:300, 1300:1700] - np.array([40, 90, 60])).max(axis=-1) < 30).mean()  # outside the oval
    assert green > .2  # the (fake) satellite picture
    red = (frame[..., 0] > 180) & (frame[..., 1] < 90)
    assert red.mean() > .005  # the red/white hatched oval
    white = (frame > 230).all(axis=-1)
    assert white[30:140, 40:500].mean() > .02 and white[H_ - 60:H_, 760:1160].mean() > .005  # badge + dots, ŞEMATİK note
    assert white[H_ - 40:H_, W_ - 200:W_].mean() > .01  # © Mapbox
    frame = render('arrow', 'Lyon > Marseille', tmp_path)
    yellow = (frame[..., 0] > 200) & (frame[..., 1] > 170) & (frame[..., 2] < 90)
    assert yellow.mean() > .002  # the yellow [OK] line


W_, H_ = 1920, 1080


def test_no_key_falls_back_to_the_drawn_map_with_a_turkish_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(satellite, 'FACTORY', lambda: MapboxSatelliteProvider('', 'https://api.mapbox.com/v4/x/{z}/{x}/{y}.jpg'))
    frame = render('region', 'Bretagne', tmp_path)
    assert 'Mapbox API anahtarı girilmeli' in relief.LAST_WARNING
    assert (frame.sum(axis=-1) < 140).mean() > .3  # the dark drawn map
    relief.LAST_WARNING = ''
    monkeypatch.setattr(satellite, 'FACTORY', lambda: MapboxSatelliteProvider('pk.bad-key-123', 'https://api.mapbox.com/v4/x/{z}/{x}/{y}.jpg', transport=fake(401)))
    render('region', 'Bretagne', tmp_path)
    assert 'kabul edilmedi' in relief.LAST_WARNING
    relief.LAST_WARNING = ''


def test_settings_and_look_without_key(tmp_path, monkeypatch):
    client, pid, world, fake_ai = F.make(tmp_path, monkeypatch)
    try:
        look = client.get(f'/api/projects/{pid}/look', headers=F.HEADERS).json()
        option = next(m for m in look['map_styles'] if m['id'] == 'satellite')
        assert option['disabled'] is True and option['note'] == 'Mapbox API anahtarı girilmeli (Ayarlar).'
        assert [m['id'] for m in look['map_styles']][:2] == ['relief', 'dark']  # the other styles stay
        r = client.put(f'/api/projects/{pid}/look', json={'map_style': 'satellite'}, headers=F.HEADERS)
        assert r.status_code >= 400 and 'Mapbox API anahtarı' in r.json()['message']
        r = client.put('/api/settings/mapbox', json={'api_key': 'pk.synthetic-mapbox-key-4444'}, headers=F.SETTINGS)
        assert r.status_code == 200 and 'synthetic' not in r.text  # stored masked, never echoed
        look = client.get(f'/api/projects/{pid}/look', headers=F.HEADERS).json()
        assert next(m for m in look['map_styles'] if m['id'] == 'satellite')['disabled'] is False
        r = client.put(f'/api/projects/{pid}/look', json={'map_style': 'satellite'}, headers=F.HEADERS)
        assert r.status_code == 200 and r.json()['map_style'] == 'satellite'
        assert 'Uydu' in client.get('/static/render.js').text or 'map_styles' in client.get('/static/render.js').text
        assert 'mapbox' in client.get('/static/settings.js').text
    finally:
        client.__exit__(None, None, None)
