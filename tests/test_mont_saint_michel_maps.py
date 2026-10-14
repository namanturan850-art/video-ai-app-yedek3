"""Mont-Saint-Michel (French script): every map marker becomes a satellite map
(oblique view), none falls back to stock footage, and every map clip is a
valid local file. Small places come from the town list (Avranches) or Mapbox
Geocoding (Genêts); an unknown place is drawn at the nearest known place with
a Turkish warning. No Mapbox account here: the tilted pictures, the tiles and
the geocoding answers come from fakes; the real API was not called."""
import subprocess

import httpx
import numpy as np
from PIL import Image

import test_fast_media as F
import test_media_director_topics as T
from test_satellite_oblique import FakeMapbox
from app.channels import DEFAULT_STYLE
from app.motion.templates import build
from app.motion.templates_extra import parse
from app.providers import geocoding, satellite
from app.stock.download import asset_path

SAT = {**DEFAULT_STYLE, 'map_style': 'satellite', 'map_style_chosen': True}
FR = """# Le Mont-Saint-Michel

Au large de la Normandie se dresse un rocher couronné d'une abbaye. [HARİTA: Mont-Saint-Michel]
La petite ville d'Avranches veille sur la baie depuis des siècles. [YAKINLAŞ: Avranches]
Les pèlerins traversaient les sables à pied depuis le village de Genêts. [OK: Genêts > Mont-Saint-Michel]
Toute la côte normande vit au rythme des marées. [BÖLGE: Normandie]
La Normandie et la Bretagne se disputent le rocher depuis toujours. [KARŞILAŞTIR: Normandie | Bretagne]
Un ancien hameau oublié se trouvait jadis près du Mont-Saint-Michel. [HARİTA: Saint-Quorvinec-des-Grèves]
"""
GEO = {'genêts': [-1.4767, 48.6847]}  # [lon, lat] as GeoJSON


def fake_geocoding(monkeypatch, asked):
    def handler(request):
        name = request.url.params['q']
        asked.append(name)
        assert request.url.params['access_token'].startswith('pk.')
        point = GEO.get(name.casefold())
        features = [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': point}, 'properties': {}}] if point else []
        return httpx.Response(200, json={'type': 'FeatureCollection', 'features': features})
    monkeypatch.setattr(geocoding, 'FACTORY', lambda: geocoding.MapboxGeocodingProvider('pk.test-key-123', transport=httpx.MockTransport(handler)))


def test_every_map_marker_is_satellite_in_the_satellite_style():
    for kind, value in (('zoom', 'Avranches'), ('zoom', 'Pontorson'), ('region', 'Normandie'), ('compare', 'Normandie | Bretagne'),
                        ('empire', 'Roma 27 v. Chr.-117')):
        spec = parse(kind, value) if kind != 'compare' else __import__('app.motion.templates_extra', fromlist=['x']).relief_marker('compare', value)
        elements = build(spec, SAT, 4., 2., 'fr')['elements']
        assert [e['props'].get('theme') for e in elements if e['type'] == 'relief'] == ['satellite'], (kind, value)
        assert not any(e['type'] in ('map', 'geopin', 'geoarea') for e in elements), (kind, value)  # no drawn (dark neon) map at all
    marker = build({'template': 'map', 'data': {'place': 'Mont-Saint-Michel', 'label': '', 'lat': 48.636, 'lon': -1.5115}, 'emphasis': ''}, SAT, 4., 2., 'fr')
    assert [e['props'].get('theme') for e in marker['elements'] if e['type'] == 'relief'] == ['satellite']


def test_mont_saint_michel_script_end_to_end(tmp_path, monkeypatch):
    client, pid, world, fake = F.make(tmp_path, monkeypatch, FR, language='fr', fast=False)
    asked = []
    try:
        provider = FakeMapbox()
        monkeypatch.setattr(satellite, 'FACTORY', lambda: provider)
        monkeypatch.setattr(satellite, 'OBLIQUE', lambda: True)
        fake_geocoding(monkeypatch, asked)
        client.put('/api/settings/mapbox', json={'api_key': 'pk.synthetic-mapbox-key-4444'}, headers=F.HEADERS | F.SETTINGS)
        assert client.put(f'/api/projects/{pid}/look', json={'map_style': 'satellite'}, headers=F.HEADERS).status_code == 200
        client.app.state.stock.clip_scorer = F.clip_fake(world, [])
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed', view['job']
        marked = [s for s in view['slots'] if ((s['selected_media'] or {}).get('source_metadata') or {}).get('owner_hint')]
        types = sorted(s['selected_media']['source_metadata']['owner_hint']['type'] for s in marked)
        assert types == ['arrow', 'compare', 'map', 'map', 'region', 'zoom'], types  # all six markers: no stock video in a marked slot
        folder = client.app.state.projects._path(pid)
        for slot in marked:
            media = slot['selected_media']
            assert media['provider'] == 'generated' and media['source_metadata']['motion']['template'] in ('relief', 'map', 'zoom'), media
            assert slot['status'] == 'complete' and 'Yerel dosya eksik' not in slot.get('message', '')
            asset_path(client.app.state.projects, pid, media)  # the file exists under a valid name
            frame = tmp_path / 'f.png'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '1.5', '-i', str(folder / media['local_path']), '-frames:v', '1', str(frame)], check=True)
            pixels = np.asarray(Image.open(frame).convert('RGB'), dtype=np.int16)
            green = ((pixels[..., 1] > pixels[..., 2] + 10) & (pixels[..., 1] > 60)).mean()
            assert green > .2, (slot['order'], green)  # the (fake) satellite landscape, not the dark navy map
        assert len(provider.calls) >= 6 and all(call[4] >= 55 for call in provider.calls)  # every map: one tilted (pitch 55-60) picture
        assert 'Genêts' in asked  # the town list lacks it: Mapbox Geocoding
        warnings = ' '.join(view['job']['progress'].get('marker_warnings') or [])
        assert 'Saint-Quorvinec-des-Grèves' in warnings and 'en yakın bilinen yer (Mont-Saint-Michel)' in warnings, warnings
        # the answers are cached: a second job asks Mapbox nothing again
        before = len(asked)
        from app.motion.places import locate
        assert locate('Genêts')['source'] == 'mapbox' and len(asked) == before
    finally:
        client.__exit__(None, None, None)


def test_oblique_failure_clip_keeps_a_valid_file_name(tmp_path, monkeypatch):
    """The satellite problem (oblique picture refused) used to save the clip as
    <key>-fallback-xxxx.mp4, which the media screen read as a missing file."""
    from app.motion.clips import render_clip
    from app.providers.satellite import SatelliteError
    monkeypatch.setattr(satellite, 'FACTORY', lambda: FakeMapbox(static_error=SatelliteError('key_rejected', 'Mapbox anahtarı kabul edilmedi (401/403).')))
    monkeypatch.setattr(satellite, 'OBLIQUE', lambda: True)
    path, _, _ = render_clip(tmp_path, parse('zoom', 'Avranches'), SAT, 3., 1.5, language='fr')
    import re
    assert re.fullmatch(r'[a-f0-9]{32}\.mp4', path.name), path.name
