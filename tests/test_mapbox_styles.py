"""Style selection, actual outbound URLs, private previews and shared render style.
Mapbox responses are synthetic; these tests never claim live account access.
"""
from io import BytesIO
import math

import httpx
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers import satellite
from app.providers.mapbox_styles import static_template
from app.settings import MapboxSettings

HEADERS = {'X-AI-Video-Studio': 'settings'}
CUSTOM = 'mapbox://styles/my-account/my-style'


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'data')) as c:
        yield c


def png(width=600, height=340):
    stream = BytesIO()
    Image.new('RGB', (width, height), '#346d82').save(stream, 'PNG')
    return stream.getvalue()


def test_catalog_and_persistent_selection_keep_secret_private(client):
    r = client.get('/api/settings/mapbox/styles')
    assert r.status_code == 200
    data = r.json()
    assert len(data['styles']) == 9 and data['selected_style'] == '' and not data['has_api_key']
    saved = client.put('/api/settings/mapbox', headers=HEADERS,
        json={'api_key': 'pk.private-synthetic-key', 'selected_style': 'mapbox://styles/mapbox/dark-v11'})
    assert saved.status_code == 200, saved.text
    assert 'pk.private-synthetic-key' not in saved.text
    assert 'pk.private-synthetic-key' not in client.get('/api/settings/mapbox/styles').text
    service = client.app.state.settings
    config = service.mapbox_config()
    assert '/mapbox/dark-v11/static/' in config['static_url']
    assert config['api_key'] == 'pk.private-synthetic-key'
    # Reopening the vault uses the saved choice.
    from app.settings import SettingsService
    assert SettingsService(service.store).mapbox_config()['selected_style'] == config['selected_style']


def test_add_select_and_remove_custom_style_atomically(client):
    body = {'custom_styles': [{'uri': CUSTOM, 'name': 'Benim haritam'}], 'selected_style': CUSTOM}
    r = client.put('/api/settings/mapbox', headers=HEADERS, json=body)
    assert r.status_code == 200, r.text
    catalog = client.get('/api/settings/mapbox/styles').json()
    assert catalog['styles'][-1] == {'uri': CUSTOM, 'name': 'Benim haritam', 'custom': True}
    assert catalog['selected_style'] == CUSTOM
    # Partial saves preserve the style and custom list.
    client.put('/api/settings/mapbox', headers=HEADERS, json={'oblique': False})
    assert client.app.state.settings.mapbox_config()['selected_style'] == CUSTOM
    refused = client.put('/api/settings/mapbox', headers=HEADERS, json={'custom_styles': []})
    assert refused.status_code == 422
    r = client.put('/api/settings/mapbox', headers=HEADERS, json={'custom_styles': [], 'selected_style': ''})
    assert r.status_code == 200


@pytest.mark.parametrize('uri', ['https://evil.example/style', 'mapbox://styles/x/y?access_token=secret',
    'mapbox://styles/x/../../bad', 'mapbox://styles/user/stil#secret',
    'mapbox://styles/user/stil/extra', 'mapbox://styles/user/', 'mapbox://styles/user/a b'])
def test_style_uri_rejects_urls_tokens_and_path_injection(client, uri):
    r = client.put('/api/settings/mapbox', headers=HEADERS,
                   json={'custom_styles': [{'uri': uri, 'name': 'Test'}], 'selected_style': uri})
    assert r.status_code == 422
    assert client.get('/api/settings/mapbox/styles').json()['custom_styles'] == []


def test_unregistered_and_duplicate_styles_rejected(client):
    assert client.put('/api/settings/mapbox', headers=HEADERS, json={'selected_style': CUSTOM}).status_code == 422
    item = {'uri': CUSTOM, 'name': 'Test'}
    assert client.put('/api/settings/mapbox', headers=HEADERS, json={'custom_styles': [item, item]}).status_code == 422


def test_missing_key_preview_and_cross_origin_guards(client):
    assert client.post('/api/settings/mapbox/style-preview', json={'uri': ''}).status_code == 403
    assert client.post('/api/settings/mapbox/style-preview', headers={**HEADERS, 'Origin': 'https://elsewhere.example'}, json={'uri': ''}).status_code == 403
    r = client.post('/api/settings/mapbox/style-preview', headers=HEADERS, json={'uri': ''})
    assert r.status_code == 503 and r.json()['category'] == 'missing_key'
    assert client.post('/api/settings/mapbox/style-preview', headers=HEADERS, json={'uri': CUSTOM}).status_code == 422
    assert client.post('/api/settings/mapbox/style-preview', headers=HEADERS, json={'uri': {}}).status_code == 422


def test_preview_uses_server_key_fixed_host_and_cache(client, monkeypatch, caplog):
    import logging
    caplog.set_level(logging.INFO, logger='httpx')
    client.put('/api/settings/mapbox', headers=HEADERS, json={'api_key': 'pk.private-synthetic-key'})
    requests = []
    original = satellite.MapboxSatelliteProvider
    def respond(request):
        requests.append(request)
        assert request.url.host == 'api.mapbox.com'
        assert request.url.params['access_token'] == 'pk.private-synthetic-key'
        assert '/mapbox/streets-v12/static/' in request.url.path
        return httpx.Response(200, content=png(), headers={'content-type': 'image/png'})
    def factory(*args, **kwargs):
        return original(*args, **kwargs, transport=httpx.MockTransport(respond))
    monkeypatch.setattr(satellite, 'MapboxSatelliteProvider', factory)
    for _ in range(2):
        r = client.post('/api/settings/mapbox/style-preview', headers=HEADERS, json={'uri': 'mapbox://styles/mapbox/streets-v12'})
        assert r.status_code == 200 and r.headers['content-type'] == 'image/png'
        assert r.content == png() and 'private-synthetic' not in str(r.headers)
    assert len(requests) == 1  # cache prevents another billed request
    assert 'pk.private-synthetic-key' not in caplog.text


def test_flat_and_tilted_views_request_the_same_selected_style(monkeypatch):
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(200, content=png(), headers={'content-type': 'image/png'})
    p = satellite.MapboxSatelliteProvider('pk.test-key', MapboxSettings().tile_url,
        static_url=static_template(CUSTOM), selected_style=CUSTOM, transport=httpx.MockTransport(respond))
    try:
        p.tile(3, 4, 2)
        p.static(22, 48, 4, 30, 45, 300, 170)
    finally:
        p.client.close()
    assert all('/my-account/my-style/static/' in r.url.path for r in seen)
    # A tile's centre and footprint are converted to Static Images logical zoom.
    camera = seen[0].url.path.split('/static/')[1].split('/')[0].split(',')
    assert float(camera[0]) == pytest.approx(22.5)
    assert float(camera[1]) == pytest.approx(math.degrees(math.atan(math.sinh(math.pi * (1-2*2.5/8)))), abs=1e-5)
    assert float(camera[2]) == 2 and seen[0].url.path.endswith('/256x256@2x')


def test_style_selection_changes_scene_cache_identity(client):
    from app.motion.templates_extra import satellite_props
    from app.motion.clips import scene_key
    service = client.app.state.settings
    before = satellite_props('tr')
    service.save('mapbox', {'selected_style': 'mapbox://styles/mapbox/light-v11'})
    after = satellite_props('tr')
    assert before != after
    assert scene_key(before) != scene_key(after)
    provider_key = satellite.STYLE_KEY()
    assert provider_key == 'mapbox://styles/mapbox/light-v11'


def test_legacy_override_survives_switching_back(client):
    service = client.app.state.settings
    old = 'https://api.mapbox.com/styles/v1/owner/legacy/static/{lon},{lat},{zoom},{bearing},{pitch}/{width}x{height}@2x'
    service.save('mapbox', {'static_url': old})
    service.save('mapbox', {'selected_style': 'mapbox://styles/mapbox/dark-v11'})
    assert service.mapbox_config()['static_url'] != old
    service.save('mapbox', {'selected_style': ''})
    assert service.mapbox_config()['static_url'] == old


def test_selected_style_reaches_real_native_video(client, tmp_path, monkeypatch):
    import numpy as np
    from test_satellite_map import render
    client.app.state.settings.save('mapbox', {'api_key': 'pk.test-render-key',
        'selected_style': 'mapbox://styles/mapbox/dark-v11', 'oblique': True})
    seen = []
    original = satellite.MapboxSatelliteProvider
    def respond(request):
        seen.append(request)
        return httpx.Response(200, content=png(), headers={'content-type': 'image/png'})
    monkeypatch.setattr(satellite, 'MapboxSatelliteProvider',
        lambda *args, **kwargs: original(*args, **kwargs, transport=httpx.MockTransport(respond)))
    frame = render('region', 'Bretagne', tmp_path)
    assert seen and all('/mapbox/dark-v11/static/' in r.url.path for r in seen)
    assert ((np.abs(frame - np.array([52, 109, 130]))).max(axis=-1) < 25).mean() > .15
